import maya.api.OpenMaya as om
import random
import math


def maya_useNewAPI():
    """
    Tell Maya this plugin uses the python API 2.0
    """
    pass


command_instance_counter = 1


class RandomExtrudeCmd(om.MPxCommand):
    COMMAND_NAME = "randomExtrude"
    THICKNESS_RANGE_FLAG = ["-tr", "-thicknessRange",
                            (om.MSyntax.kDouble, om.MSyntax.kDouble)]
    OFFSET_FLAG = ["-o", "-offset"]
    MAX_FACE_TOGETHER = ["-mf", "-maxFaces", om.MSyntax.kLong]

    MESSAGE_INFORMATION_NO_SELECTION = "No selection found"

    def __init__(self):
        super(RandomExtrudeCmd, self).__init__()

        # to track number of times the command is instantiated
        global command_instance_counter
        self.command_execution = command_instance_counter
        command_instance_counter = command_instance_counter + 1

    def isUndoable(self):
        return True

    @ classmethod
    def creator(cls):
        return RandomExtrudeCmd()

    @classmethod
    def create_syntax(cls):

        syntax = om.MSyntax()

        syntax.enableEdit = False
        syntax.enableQuery = False

        syntax.addFlag(*cls.THICKNESS_RANGE_FLAG)
        syntax.addFlag(*cls.OFFSET_FLAG)
        syntax.addFlag(*cls.MAX_FACE_TOGETHER)

        syntax.useSelectionAsDefault(True)

        return syntax

    def doIt(self, args):
        ''' Parse arguments and set up main objects used in the command. '''
        self.dag_modifier = om.MDagModifier()

        # parse  the arguments
        try:
            arg_db = om.MArgDatabase(self.syntax(), args)
        except:
            self.displayError("Error parsing arguments")
            raise

        self.thickness_range_set = arg_db.isFlagSet(
            RandomExtrudeCmd.THICKNESS_RANGE_FLAG[0])

        if self.thickness_range_set:
            self.thickness_range = [arg_db.flagArgumentDouble(RandomExtrudeCmd.THICKNESS_RANGE_FLAG[0], 0),
                                    arg_db.flagArgumentDouble(RandomExtrudeCmd.THICKNESS_RANGE_FLAG[0], 1)]

        self.use_offset = arg_db.isFlagSet(RandomExtrudeCmd.OFFSET_FLAG[0])

        if arg_db.isFlagSet(RandomExtrudeCmd.MAX_FACE_TOGETHER[0]):
            self.max_face_together = arg_db.flagArgumentInt(
                RandomExtrudeCmd.MAX_FACE_TOGETHER[0], 0)
        else:
            self.max_face_together = 20

        # check for user selection
        selection_list = om.MGlobal.getActiveSelectionList()
        if selection_list.isEmpty():
            # RuntimeWarning(self.MESSAGE_INFORMATION_NO_SELECTION)
            print(self.MESSAGE_INFORMATION_NO_SELECTION)
            return None

        # TODO: need to perform extra checks here to make sure we have a proper selection
        self.mesh_dag_path = selection_list.getDagPath(0)

        self.mesh_fn = om.MFnMesh(self.mesh_dag_path)
        self.poly_it = om.MItMeshPolygon(self.mesh_dag_path)

        self.mesh_points = self.mesh_fn.getPoints()

        self.output_mesh_transform_obj = self.dag_modifier.createNode(
            'transform')

        # get the group of faces that will be extruded together
        self.face_groups = self.get_face_groups()

        self.output_mesh_obj = self.create_extrusions(self.face_groups)

        # Create the shading node.
        self.shading_node_name = 'randomExtrudeMaterial' + \
            str(self.command_execution)
        self.dag_modifier.commandToExecute(
            'shadingNode -asShader -name ' + self.shading_node_name + ' lambert;')
        self.dag_modifier.commandToExecute(
            'setAttr "' + self.shading_node_name + '.color" -type double3 0.5 0.5 0.5;')

        # Create the shading group.
        self.shading_group_name = 'randomExtrudeGroup' + \
            str(self.command_execution)
        self.dag_modifier.commandToExecute(
            'sets -renderable true -noSurfaceShader true -empty -name ' + self.shading_group_name + ';')
        self.dag_modifier.commandToExecute(
            'connectAttr -f ' + self.shading_node_name + '.outColor ' + self.shading_group_name + '.surfaceShader;')

        self.redoIt()

    def redoIt(self):
        self.dag_modifier.doIt()

        mesh_dag_path = om.MDagPath()
        dag_shape_node_fn = om.MFnDagNode(self.output_mesh_obj)
        mesh_dag_path = dag_shape_node_fn.getPath()

        self.dag_modifier.commandToExecute(
            'sets -e -forceElement ' + self.shading_group_name + ' ' + mesh_dag_path.fullPathName())

        self.dag_modifier.doIt()

        self.dag_modifier.commandToExecute(
            'delete -ch')

        self.dag_modifier.doIt()

    def has_edge(self, id, edgeIt: om.MItMeshEdge):
        """
        Return if the argument id is contained in the mesh 
        """
        edgeIt.reset()
        while not edgeIt.isDone():
            if edgeIt.index() == id:
                return True
            edgeIt.next()
        return False

    def create_extrusions(self, face_groups):
        input_mesh_fn = om.MFnMesh(self.mesh_dag_path)

        output_mesh_obj = input_mesh_fn.copy(
            input_mesh_fn.object(),  parent=self.output_mesh_transform_obj)

        output_mesh_fn = om.MFnMesh(output_mesh_obj)
        output_mesh_poly_it = om.MItMeshPolygon(output_mesh_obj)
        output_mesh_edge_it = om.MItMeshEdge(output_mesh_obj)

        # create a set of edges that will be deleted to combine the faces in each face group
        edges_to_delete = set()
        for face_group in face_groups:

            for face in face_group:
                output_mesh_poly_it.setIndex(face)

                edges = output_mesh_poly_it.getEdges()
                for edge in edges:
                    output_mesh_edge_it.setIndex(edge)

                    connected_faces = output_mesh_edge_it.getConnectedFaces()

                    if len(connected_faces) >= 2 and all([(connected_face in face_group) for connected_face in connected_faces]):
                        edges_to_delete.add(edge)

        # delete the edges as long as the edge is still in the mesh
        for edge in edges_to_delete:
            if self.has_edge(edge, output_mesh_edge_it):
                output_mesh_fn.deleteEdge(edge, modifier=self.dag_modifier)

        output_mesh_poly_it.reset()

        # perform the extrusion randomly based on arguments
        while not output_mesh_poly_it.isDone():
            if self.thickness_range_set:
                extrude_amount = random.uniform(
                    self.thickness_range[0], self.thickness_range[1])
            else:
                extrude_amount = random.uniform(0.001, 0.1)

            offset_max = math.sqrt(output_mesh_poly_it.getArea())/math.pi

            # perform the extrusions
            if self.use_offset:
                offset = random.uniform(0.1, 0.5) * offset_max
                output_mesh_fn.extrudeFaces([output_mesh_poly_it.index()], translation=extrude_amount*om.MFloatVector(output_mesh_fn.getPolygonNormal(
                    output_mesh_poly_it.index())),  extrudeTogether=True, offset=offset)
                output_mesh_fn.updateSurface()
            else:
                output_mesh_fn.extrudeFaces([output_mesh_poly_it.index()], translation=extrude_amount*om.MFloatVector(output_mesh_fn.getPolygonNormal(
                    output_mesh_poly_it.index())),  extrudeTogether=True)
                output_mesh_fn.updateSurface()

            output_mesh_poly_it.next()

        input_mesh_fn.setName('randomExtrudeShape' +
                              str(self.command_execution))

        transformFn = om.MFnTransform(self.output_mesh_transform_obj)
        transformFn_og_mesh = om.MFnTransform(self.mesh_dag_path)
        # print(transformFn_og_mesh.translation())
        transformFn.setTransformation(transformFn_og_mesh.transformation())

        return output_mesh_obj

    def undoIt(self):
        self.dag_modifier.undoIt()

    def get_face_groups(self):
        """
        Create the groups of faces that will be extruded together. 
        """
        visited = set()

        self.poly_it.reset()
        face_groups = []

        while not self.poly_it.isDone():
            # if the face has not been flagged for extrusion then get random group of nearby faces to extrude with it
            if self.poly_it.index() not in visited:
                face_group = self.get_nearby_faces(visited)
                face_groups.append(face_group)
            self.poly_it.next()
        return(face_groups)

    def get_nearby_faces(self, visited: set):
        nearby_faces = [self.poly_it.index()]
        visited.add(self.poly_it.index())

        connected_faces = self.poly_it.getConnectedFaces()
        valid_faces = self.extract_valid_faces(
            nearby_faces[0], visited, connected_faces)
        nearby_faces = nearby_faces + valid_faces

        return(nearby_faces)

    def extract_valid_faces(self, start, visited, connected_faces):
        face_count = 1
        valid_faces = []
        for face in connected_faces:
            if face_count > self.max_face_together:
                break

            dot_prod = om.MFloatVector(self.mesh_fn.getPolygonNormal(
                face)) * om.MFloatVector(self.mesh_fn.getPolygonNormal(start))
            if (face not in visited) and dot_prod == 1:
                valid_faces.append(face)
                visited.add(face)
                face_count = face_count + 1

        return(valid_faces)


def initializePlugin(plugin):
    """
    """
    vendor = "Matthew Gould"
    version = "0.0.1"

    plugin_fn = om.MFnPlugin(plugin, vendor, version)

    try:
        plugin_fn.registerCommand(
            RandomExtrudeCmd.COMMAND_NAME, RandomExtrudeCmd.creator, RandomExtrudeCmd.create_syntax)
    except:
        om.MGlobal.displayError(
            "Failed to register command: {0}".format(RandomExtrudeCmd))


def uninitializePlugin(plugin):
    """
    """
    plugin_fn = om.MFnPlugin(plugin)
    try:
        plugin_fn.deregisterCommand(RandomExtrudeCmd.COMMAND_NAME)
    except:
        om.MGlobal.displayError(
            "Failed to deregister command: {0}".format(RandomExtrudeCmd))

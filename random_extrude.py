import maya.api.OpenMaya as om
import maya.cmds as cmds
import maya.mel as mel
import random
import math


def maya_useNewAPI():
    """
    Tell Maya this plugin uses the python API 2.0
    """
    pass


class RandomExtrudeCmd(om.MPxCommand):
    COMMAND_NAME = "randomExtrude"
    THICKNESS_RANGE_FLAG = ["-tr", "-thicknessRange",
                            (om.MSyntax.kDouble, om.MSyntax.kDouble)]
    OFFSET_FLAG = ["-o", "-offset"]
    MAX_FACE_TOGETHER = ["-mf", "-maxFaces", om.MSyntax.kLong]

    MESSAGE_INFORMATION_NO_SELECTION = "No selection found"

    def __init__(self):
        super(RandomExtrudeCmd, self).__init__()

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
            print("No selection")
            return None

        selection_it = om.MItSelectionList(selection_list)

        while not selection_it.isDone():
            obj = selection_it.getDependNode()

            # get the face iterator and mesh functions then make call to create the extrusions
            if selection_it.hasComponents():
                dag_components, obj_components = selection_it.getComponent()

                mesh_fn = om.MFnMesh(dag_components)
                poly_it = om.MItMeshPolygon(dag_components, obj_components)

                faces = []
                while not poly_it.isDone():
                    faces.append(int(poly_it.index()))
                    poly_it.next()
            else:
                dag = selection_it.getDagPath()
                mesh_fn = om.MFnMesh(dag)
                poly_it = om.MItMeshPolygon(dag)
                faces = range(0, mesh_fn.numPolygons)

            self.add_random_extrusions(mesh_fn, poly_it, faces)

            selection_it.next()

    def redoIt(self):
        pass

    def add_random_extrusions(self, mesh_fn, poly_it, selected_faces):

        # to keep track of which faces are already flagged for extrusion
        visited = set(range(0, mesh_fn.numPolygons))

        # to ensure that only the selected faces are extruded
        visited = visited.difference(selected_faces)

        # get the group of faces that will be extruded together
        face_groups = self.get_face_groups(mesh_fn, poly_it, visited)

        for face_group in face_groups:

            if self.thickness_range_set:
                extrude_amount = random.uniform(
                    self.thickness_range[0], self.thickness_range[1])
            else:
                extrude_amount = random.uniform(0, 0.1)

            # determine an upper bound on the offset amount
            area = 0
            for face in face_group:
                poly_it.setIndex(face)
                area = area + poly_it.getArea()

            offset_max = math.sqrt(area/(len(face_group)))/math.pi

            # perform the extrusions
            if self.use_offset:
                offset = random.uniform(0.1, 0.9) * offset_max
                mesh_fn.extrudeFaces(face_group, translation=extrude_amount*om.MFloatVector(mesh_fn.getPolygonNormal(
                    face_group[0])),  extrudeTogether=True, offset=offset)
            else:
                mesh_fn.extrudeFaces(face_group, translation=extrude_amount*om.MFloatVector(mesh_fn.getPolygonNormal(
                    face_group[0])),  extrudeTogether=False)

        mesh_fn.updateSurface()
        cmds.delete(ch=1)

    def get_face_groups(self, mesh: om.MFnMesh, poly_it: om.MItMeshPolygon, visited: set):
        poly_it.reset()
        face_groups = []
        while not poly_it.isDone():
            # if the face has not been flagged for extrusion then get random group of nearby faces to extrude with it
            if poly_it.index() not in visited:
                face_group = self.get_nearby_faces(mesh, poly_it, visited)
                face_groups.append(face_group)
            poly_it.next()
        return(face_groups)

    def get_nearby_faces(self, mesh: om.MFnMesh, poly_it: om.MItMeshPolygon, visited: set):
        cmds.select(cl=True)
        cmds.select(mesh.name() + ".f[" + str(poly_it.index()) + "]")

        # tranverse random number of times to expand the nearby faces
        # TODO: look into translating the mel command
        for i in range(random.randint(1, 3)):
            mel.eval('PolySelectTraverse 1')

        selection_list = om.MGlobal.getActiveSelectionList()
        selection_it = om.MItSelectionList(selection_list)

        dag_components, obj_components = selection_it.getComponent()

        poly_traverse_it = om.MItMeshPolygon(dag_components, obj_components)

        # add the first face
        nearby_faces = [poly_it.index()]
        visited.add(poly_it.index())
        face_count = 1

        # add the remaining faces checkig if they have been visited and if they have a valid dot product
        while not poly_traverse_it.isDone() and face_count < self.max_face_together:
            face = poly_traverse_it.index()

            # ensure that the face has a similiar normal
            dot_prod = om.MFloatVector(mesh.getPolygonNormal(
                face)) * om.MFloatVector(mesh.getPolygonNormal(nearby_faces[0]))
            if (face not in visited) and dot_prod > 0:
                nearby_faces.append(face)
                visited.add(face)
                face_count = face_count + 1
            poly_traverse_it.next()

        cmds.select(cl=True)
        return(nearby_faces)


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

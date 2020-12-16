
#
# This script is licensed as public domain.
#

from .utils import PathType, GetFilepath, CheckFilepath, \
                   FloatToString, Vector3ToString, Vector4ToString, \
                   WriteXmlFile,WriteStringFile, SDBMHash, getLodSetWithID, getObjectWithID,\
                   PrepareSceneHeaderFile,PrepareGlobalHeader,WriteSceneHeaderFile
from xml.etree import ElementTree as ET
from mathutils import Vector, Quaternion, Matrix
import bpy,copy
import os
import logging,traceback
import math

jsonNodetreeAvailable = True
log = logging.getLogger("ExportLogger")

from .addon_jsonnodetree import JSONNodetree
from .addon_jsonnodetree import JSONNodetreeUtils

usedMaterialTrees = []
 
#-------------------------
# Scene and nodes classes
#-------------------------

# Options for scene and nodes export
class SOptions:
    def __init__(self):
        self.doIndividualPrefab = False
        self.doCollectivePrefab = False
        self.doScenePrefab = False
        self.SceneCreateZone = False
        self.ZoneTexture = "None"
        self.noPhysics = False
        self.individualPhysics = False
        self.individualPrefab_onlyRootObject = True
        self.globalPhysics = False
        self.mergeObjects = False
        self.shape = None
        self.shapeItems = None
        self.trasfObjects = False
        self.exportUserdata = True
        self.globalOrigin = False
        self.orientation = Quaternion((1.0, 0.0, 0.0, 0.0))
        self.wiredAsEmpty = False
        self.exportGroupsAsObject = True
        self.exportObjectCollectionAsTag = True
        self.objectsPath = "Objects"


class UrhoSceneMaterial:
    def __init__(self):
        # Material name
        self.name = None
        # List\Tuple of textures
        self.texturesList = None

    def Load(self, uExportData, uGeometry):
        self.name = uGeometry.uMaterialName
        for uMaterial in uExportData.materials:
            if uMaterial.name == self.name:
                self.texturesList = uMaterial.getTextures()
                break


class UrhoSceneModel:
    def __init__(self):
        # Model name
        self.name = None
        # Blender object name
        self.objectName = None
        # Parent Blender object name
        self.parentObjectName = None
        # Model type
        self.type = None
        # List of UrhoSceneMaterial
        self.materialsList = []
        # Model bounding box
        self.boundingBox = None
        # Model position
        self.position = Vector()
        # Position with collection offset applied
        self.colInstPosition = Vector()
        # Model rotation
        self.rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
        # Model scale
        self.scale = Vector((1.0, 1.0, 1.0))

        self.parent_bone = None

    def Load(self, uExportData, uModel, objectName, sOptions):
        self.name = uModel.name

        self.blenderObjectName = objectName
        object = bpy.data.objects[objectName]

        if objectName:

            transObject = object

            bone_parent = False


            if object.parent and object.parent.type=="ARMATURE":

                if object.parent_type=="BONE":
                    bone_parent = True

                    # we need to parent the bone-parented objects to one child of the armature (due to matrix-problems)
                    # whoever finds a better way is welcome to use this. until then let's do the hack
                    old_matrix = object.matrix_local.copy()
                    old_parent = object.parent
                    old_parent_matrix = object.matrix_parent_inverse.copy()
                    self.parent_bone = object.parent_bone

                    print("FOUND PARENT Bone parenting!")
                    print("FOUND PARENT Armature!")
                    print("FOUND PARENT Armature!")
                    try:
                        # we need to add the object to one child of the armature
                        for child in object.parent.children:
                            if child != object:
                                object.parent = child
                                object.parent_type="OBJECT"
                                object.matrix_parent_inverse = child.matrix_world.inverted()                                

                                parentObject = child
                                transObject = object
                                break
                    except Exception as e:
                        print("problem: %s" % e)
                        transObject = object.parent
                        parentObject = transObject.parent
                else:
                    transObject = object.parent
                    parentObject = transObject.parent
            else:
                parentObject = transObject.parent





            # Get the local matrix (relative to parent)
            objMatrix = transObject.matrix_local
            # Reorient (normally only root objects need to be re-oriented but 
            # here we need to undo the previous rotation done by DecomposeMesh)
            if sOptions.orientation:
                om = sOptions.orientation.to_matrix().to_4x4()
                objMatrix = om @ objMatrix @ om.inverted()

            # Get pos/rot/scale

            pos = objMatrix.to_translation()   ## keep this. this actually worked well. only the positions weren't right :)
            rot = objMatrix.to_quaternion()
            scale = objMatrix.to_scale()

            self.position = Vector((pos.x, pos.z, pos.y))
            
            self.rotation = Quaternion((rot.w, -rot.x, -rot.z, -rot.y))
            self.scale = Vector((scale.x, scale.z, scale.y))

            # Get parent object
            if parentObject :
                self.parentObjectName = parentObject.name

            if bone_parent:
                object.parent=old_parent
                object.parent_bone=self.parent_bone
                object.parent_type="BONE"
                object.matrix_parent_inverse = old_parent_matrix
                object.matrix_local = old_matrix


        print("ObjectName:%s uModelName:%s bones:%s" % (uModel.name,object.name,len(uModel.bones)))
#        if (len(uModel.bones) > 0 and len(object.vertex_groups)>0) or len(uModel.morphs) > 0):
        if ( (object.type=="MESH" and (len(object.vertex_groups)>0 or object.data.shape_keys))
            or (object.type!="MESH" and (len(uModel.bones) > 0 or len(uModel.morphs) > 0))):
            self.type = "AnimatedModel"
        elif object.lodsetID>0:
            # this object has an lodset as mesh
            lodset = getLodSetWithID(object.lodsetID)
            if lodset.armatureObj :
                self.type = "AnimatedModel"
            else:
                self.type = "StaticModel"
        else:
            self.type = "StaticModel"

        for uGeometry in uModel.geometries:
            uSceneMaterial = UrhoSceneMaterial()
            uSceneMaterial.Load(uExportData, uGeometry)
            self.materialsList.append(uSceneMaterial)

        self.boundingBox = uModel.boundingBox

# Get the object quaternion rotation, convert if it uses other rotation modes
def GetQuatenion(obj):
    # Quaternion mode
    if obj.rotation_mode == 'QUATERNION':
        return obj.rotation_quaternion
    # Axis Angle mode
    if obj.rotation_mode == 'AXIS_ANGLE':
        rot = obj.rotation_axis_angle
        return Quaternion(Vector((rot[1], rot[2], rot[3])), rot[0])
    # Euler mode
    return obj.rotation_euler.to_quaternion()

# Hierarchical sorting (based on a post by Hyperboreus at SO)
class Node:
    def __init__(self, name):
        self.name = name
        self.children = []
        self.parent = None

    def to_list(self):
        names = [self.name]
        for child in self.children:
            names.extend(child.to_list())
        return names
            
class Tree:
    def __init__(self):
    	self.nodes = {}

    def push(self, item):
        name, parent = item
        if name not in self.nodes:
        	self.nodes[name] = Node(name)
        if parent:
            if parent not in self.nodes:
                self.nodes[parent] = Node(parent)
            if parent != name:
                self.nodes[name].parent = self.nodes[parent]
                self.nodes[parent].children.append(self.nodes[name])

    def to_list(self):
        names = []
        for node in self.nodes.values():
            if not node.parent:
                names.extend(node.to_list())
        return names

class UrhoScene:
    def __init__(self, blenderScene):
        # Blender scene name
        self.blenderSceneName = blenderScene.name
        # List of UrhoSceneModel
        self.modelsList = []
        # List of all files
        self.files = {}

    # name must be unique in its type
    def AddFile(self, pathType, name, fileUrhoPath):
        if not name:
            log.critical("Name null type:{:s} path:{:s}".format(pathType, fileUrhoPath) )
            return False
        if name in self.files:
            log.critical("Already added type:{:s} name:{:s}".format(pathType, name) )
            return False
        self.files[pathType+name] = fileUrhoPath
        return True

    def FindFile(self, pathType, name):
        if name is None:
            return ""
        try:
            return self.files[pathType+name]
        except KeyError:
            return ""

    def Load(self, uExportData, objectName, sOptions):
        for uModel in uExportData.models:
            uSceneModel = UrhoSceneModel()
            uSceneModel.Load(uExportData, uModel, objectName, sOptions)
            self.modelsList.append(uSceneModel)

    def SortModels(self):
        # Sort by parent-child relation
        names_tree = Tree()
        for model in self.modelsList:
            ##names_tree.push((model.objectName, model.parentObjectName))
            names_tree.push((model.name, model.parentObjectName))
        # Rearrange the model list in the new order
        orderedModelsList = []
        for name in names_tree.to_list():
            for model in self.modelsList:
                ##if model.objectName == name:
                if model.name == name:
                    orderedModelsList.append(model)
                    # No need to reverse the list, we break straightway
                    self.modelsList.remove(model)
                    break
        self.modelsList = orderedModelsList

#------------------------
# Export materials
#------------------------


def UrhoWriteMaterialTrees(fOptions,getUsedMaterials=False):
    print ("EXPORT MATERIAL-NODETREES")

    if getUsedMaterials:
        ## if the function is triggered without the export-process, the usedMaterials-array needs to be
        ## created manually
        SetUsedMaterials()

    for materialTree in usedMaterialTrees:
        fileFullPath = GetFilepath(PathType.MATERIALS, materialTree.name, fOptions)
        print("Try to export material-nodetree %s" % fileFullPath[0])        
        if os.path.exists(fileFullPath[0]) and not fOptions.fileOverwrite:
            log.error( "File already exists {:s}".format(fileFullPath[0]) )
            continue

        materialElem = ET.Element('material')

        techniques = []

        for node in materialTree.nodes:
            if node.bl_idname=="urho3dmaterials__techniqueNode":
                techniques.append(node);
            elif node.bl_idname=="urho3dmaterials__textureNode":
                textureElem = ET.SubElement(materialElem, "texture")
                textureElem.set("unit", node.prop_unit)
                textureElem.set("name", node.prop_Texture)            
            elif node.bl_idname=="urho3dmaterials__customParameterNode":
                customParamElem = ET.SubElement(materialElem, "parameter")
                customParamElem.set("name", node.prop_key)
                customParamElem.set("value", node.prop_value )           
            elif node.bl_idname=="urho3dmaterials__parameterNode":
                customParamElem = ET.SubElement(materialElem, "parameter")
                customParamElem.set("name", node.prop_name)
                customParamElem.set("value", node.prop_value )           
            elif node.bl_idname=="urho3dmaterials__standardParams" or node.bl_idname=="urho3dmaterials__pbsParams":
                paramElement = ET.SubElement(materialElem, "parameter")
                paramElement.set("name", "MatDiffColor")
                paramElement.set("value", Vector4ToString(node.prop_MatDiffColor) )            
                paramElement = ET.SubElement(materialElem, "parameter")
                paramElement.set("name", "MatSpecColor")
                paramElement.set("value", Vector4ToString(node.prop_MatSpecColor) )            
                paramElement = ET.SubElement(materialElem, "parameter")
                paramElement.set("name", "MatEmissiveColor")
                paramElement.set("value", Vector3ToString(node.prop_MatEmissiveColor) )
                paramElement = ET.SubElement(materialElem, "parameter")
                paramElement.set("name", "UOffset")
                paramElement.set("value", "%s 0 0 0" % node.prop_UOffset) 
                paramElement = ET.SubElement(materialElem, "parameter")
                paramElement.set("name", "VOffset")
                paramElement.set("value", "0 %s 0 0" % node.prop_VOffset) 

                if node.bl_idname=="urho3dmaterials__pbsParams":
                    paramElement = ET.SubElement(materialElem, "parameter")
                    paramElement.set("name", "MatEnvMapColor")
                    paramElement.set("value", Vector3ToString(node.prop_MatEnvMapColor) )                               
                    paramElement = ET.SubElement(materialElem, "parameter")
                    paramElement.set("name", "Metallic")
                    paramElement.set("value", str(node.prop_Metallic)) 
                    paramElement = ET.SubElement(materialElem, "parameter")
                    paramElement.set("name", "Roughness")
                    paramElement.set("value", str(node.prop_Roughness))
            elif node.bl_idname=="urho3dmaterials__materialNode":
                paramElement = ET.SubElement(materialElem, "cull")
                paramElement.set("value", node.prop_cull);
                paramElement = ET.SubElement(materialElem, "shadowcull")
                paramElement.set("value", node.prop_shadowcull);
                paramElement = ET.SubElement(materialElem, "fill")
                paramElement.set("value", node.prop_fill);
            elif node.bl_idname=="urho3dmaterials__DepthBiasNode":
                paramElement = ET.SubElement(materialElem, "depth")
                paramElement.set("constant", node.prop_constant);
                paramElement.set("slopescaled", node.prop_slopescaled);
            elif node.bl_idname=="urho3dmaterials__advancedMaterial":
                paramElement = ET.SubElement(materialElem, "alphatocoverage")
                paramElement.set("value", str(node.prop_alphaToCoverage));
                paramElement = ET.SubElement(materialElem, "lineantialias")
                paramElement.set("value", str(node.prop_lineAntialias));
                paramElement = ET.SubElement(materialElem, "renderorder")
                paramElement.set("value", str(node.prop_renderOrder));                
                paramElement = ET.SubElement(materialElem, "occlusion")
                paramElement.set("value", str(node.prop_occlusion)); 
                if (node.prop_vsdefines!="" or node.prop_vsdefines!=""):
                    shaderElement = ET.SubElement(materialElem, "shader")
                        
                    paramElement = ET.SubElement(shaderElement, "vsdefines")
                    paramElement.set("value", node.prop_vsdefines);  
                    paramElement = ET.SubElement(shaderElement, "psdefines")
                    paramElement.set("value", node.prop_psdefines);  
            else:
                print("Unknown MaterialNode: %s" % node.bl_idname)

        # sort the techniques according to their quality and distance
        techniques = sorted(techniques,key = lambda x: (x.prop_distance,x.prop_quality),reverse=True)

        for node in techniques:
            techniqueElem = ET.SubElement(materialElem, "technique")
            techniqueElem.set("name", node.prop_Technique)
            techniqueElem.set("quality",str(node.prop_quality))
            techniqueElem.set("loddistance",str(node.prop_distance))


        # TODO: 2.8 create nodes for this:
        # # PS defines
        # if uMaterial.psdefines != "":
        #     psdefineElem = ET.SubElement(materialElem, "shader")
        #     psdefineElem.set("psdefines", uMaterial.psdefines.lstrip())

        # # VS defines
        # if uMaterial.vsdefines != "":
        #     vsdefineElem = ET.SubElement(materialElem, "shader")
        #     vsdefineElem.set("vsdefines", uMaterial.vsdefines.lstrip())

        # if uMaterial.twoSided:
        #     cullElem = ET.SubElement(materialElem, "cull")
        #     cullElem.set("value", "none")
        #     shadowCullElem = ET.SubElement(materialElem, "shadowcull")
        #     shadowCullElem.set("value", "none")

        WriteXmlFile(materialElem, fileFullPath[0], fOptions)



def UrhoWriteMaterialsList(uScene, uModel, filepath):

    # Search for the model in the UrhoScene
    for uSceneModel in uScene.modelsList:
        if uSceneModel.name == uModel.name:
            break
    else:
        return

    # Get the model materials and their corresponding file paths
    content = ""
    for uSceneMaterial in uSceneModel.materialsList:
        file = uScene.FindFile(PathType.MATERIALS, uSceneMaterial.name)
        # If the file is missing add a placeholder to preserve the order
        if not file:
            file = "null"
        content += file + "\n"

    try:
        file = open(filepath, "w")
    except Exception as e:
        log.error("Cannot open file {:s} {:s}".format(filepath, e))
        return
    file.write(content)
    file.close()


#------------------------
# Export scene and nodes
#------------------------

def CreateNodeTreeXML(xmlroot,nodetree,nodeID,currentModel=None,currentMaterial=None,xmlCurrentModel=None,nodeName=None):
    print("CreateNodeTreeXML:%s" % nodetree.name)
    exportNodeTree = JSONNodetree.exportNodes(nodetree,True)
    # a node is in urho3d a component
    for node in exportNodeTree["nodes"]:
        print("NODE: %s" % node["label"])
        bodyElem = ET.SubElement(xmlroot, "component")
        #bodyElem.set("type", node["name"])
        bodyElem.set("type", node["label"])
        nodeID += 1
        bodyElem.set("id", "{:d}".format(nodeID))

        # node-properties are the component-attributes
        for prop in node["props"]:
            modelElem = ET.SubElement(bodyElem, "attribute")
            modelElem.set("name", prop["name"])
            value = prop["value"]
            print ("Name:%s TYPE:%s StartVal:%s" % (prop["name"],prop["type"],prop["value"]) )
            if prop["type"].startswith("vector") or prop["type"].startswith("color"):
                print("VECTOR!")
                value = value.replace("(","")
                value = value.replace(")","")
                value = value.replace(","," ")
                print("V-Result:%s" % value)
            elif prop["type"]=="enum" and value=="__Node-Mesh": # not happy with this condtion, but must work for now
                value = currentModel
            elif prop["type"]=="enum" and value=="__Node-Col-Mesh": # not happy with this condtion, but must work for now  
                if nodeName:
                    value = "Models;Models/col_%s.mdl" % nodeName
                else:
                    print("ERROR ERROR: TRIED TO SET NODE_COL_MESH for %s" % nodetree.name)
                    value = "Models;Models/ERROR.mdl"

            modelElem.set("value", value)

        if node["label"]=="StaticModel" or node["label"]=="AnimatedModel":
            modelElem = ET.SubElement(bodyElem, "attribute")
            modelElem.set("name", "Material")
            modelElem.set("value", currentMaterial)            

            if xmlCurrentModel:
                xmlroot.remove(xmlCurrentModel)

    return nodeID



## Where was the scene to generate the node again, since all was already done in scene-handling?

# Generate individual prefabs XML
# def IndividualPrefabXml(uScene, uSceneModel, sOptions):



#     # Set first node ID
#     nodeID = 0x1000000

#     # Get model file relative path
#     modelFile = uScene.FindFile(PathType.MODELS, uSceneModel.name)

#     # Gather materials
#     materials = ""
#     for uSceneMaterial in uSceneModel.materialsList:
#         file = uScene.FindFile(PathType.MATERIALS, uSceneMaterial.name)
#         materials += ";" + file

#     # Generate xml prefab content
#     rootNodeElem = ET.Element('node')
#     rootNodeElem.set("id", "{:d}".format(nodeID))
#     modelNameElem = ET.SubElement(rootNodeElem, "attribute")
#     modelNameElem.set("name", "Name")
#     modelNameElem.set("value", uSceneModel.name)

#     obj = bpy.data.objects[uSceneModel.name]

#     # the default-behaviour
#     typeElem = ET.SubElement(rootNodeElem, "component")
#     typeElem.set("type", uSceneModel.type)
#     typeElem.set("id", "{:d}".format(nodeID))

#     modelElem = ET.SubElement(typeElem, "attribute")
#     modelElem.set("name", "Model")
#     modelElem.set("value", "Model;" + modelFile)

#     materialElem = ET.SubElement(typeElem, "attribute")
#     materialElem.set("name", "Material")
#     materialElem.set("value", "Material" + materials)

#     if jsonNodetreeAvailable and hasattr(obj,"nodetreeId") and obj.nodetreeId!=-1:
#         # bypass nodeID and receive the new value
#         nodeID = CreateNodeTreeXML(rootNodeElem,obj.nodetreeId,nodeID)
#     else:
#         if not sOptions.noPhysics:
#             #Use model's bounding box to compute CollisionShape's size and offset
#             physicsSettings = [sOptions.shape] #tData.physicsSettings = [sOptions.shape, obj.game.physics_type, obj.game.mass, obj.game.radius, obj.game.velocity_min, obj.game.velocity_max, obj.game.collision_group, obj.game.collision_mask, obj.game.use_ghost] **************************************
#             shapeType = physicsSettings[0]
#             bbox = uSceneModel.boundingBox
#             #Size
#             x = bbox.max[0] - bbox.min[0]
#             y = bbox.max[1] - bbox.min[1]
#             z = bbox.max[2] - bbox.min[2]
#             shapeSize = Vector((x, y, z))
#             #Offset
#             offsetX = bbox.max[0] - x / 2
#             offsetY = bbox.max[1] - y / 2
#             offsetZ = bbox.max[2] - z / 2
#             shapeOffset = Vector((offsetX, offsetY, offsetZ))

#             bodyElem = ET.SubElement(rootNodeElem, "component")
#             bodyElem.set("type", "RigidBody")
#             bodyElem.set("id", "{:d}".format(nodeID+1))

#             collisionLayerElem = ET.SubElement(bodyElem, "attribute")
#             collisionLayerElem.set("name", "Collision Layer")
#             collisionLayerElem.set("value", "2")

#             gravityElem = ET.SubElement(bodyElem, "attribute")
#             gravityElem.set("name", "Use Gravity")
#             gravityElem.set("value", "false")

#             shapeElem = ET.SubElement(rootNodeElem, "component")
#             shapeElem.set("type", "CollisionShape")
#             shapeElem.set("id", "{:d}".format(nodeID+2))

#             shapeTypeElem = ET.SubElement(shapeElem, "attribute")
#             shapeTypeElem.set("name", "Shape Type")
#             shapeTypeElem.set("value", shapeType)

#             if shapeType == "TriangleMesh":
#                 physicsModelElem = ET.SubElement(shapeElem, "attribute")
#                 physicsModelElem.set("name", "Model")
#                 physicsModelElem.set("value", "Model;" + modelFile)

#             else:
#                 shapeSizeElem = ET.SubElement(shapeElem, "attribute")
#                 shapeSizeElem.set("name", "Size")
#                 shapeSizeElem.set("value", Vector3ToString(shapeSize))

#                 shapeOffsetElem = ET.SubElement(shapeElem, "attribute")
#                 shapeOffsetElem.set("name", "Offset Position")
#                 shapeOffsetElem.set("value", Vector3ToString(shapeOffset))

#     return rootNodeElem



def AddGroupInstanceComponent(a,m,groupFilename,offset,modelNode):

    attribID = m
    a["{:d}".format(m)] = ET.SubElement(a[modelNode], "component")
    a["{:d}".format(m)].set("type", "GroupInstance")
    a["{:d}".format(m)].set("id", str(m))
    
    m += 1

    a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(attribID)], "attribute")
    a["{:d}".format(m)].set("name", "groupFilename")
    a["{:d}".format(m)].set("value", groupFilename)
    
    # a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(attribID)], "attribute")
    # a["{:d}".format(m)].set("name", "groupOffset")
    # off = Vector3ToString(Vector( (offset.y,offset.z,offset.x) ))
    # print("EXPORT-OFFSET: %s : %s" % ( groupFilename,off ))
    # a["{:d}".format(m)].set("value", off )
    
    return m

## add userdata-attributes 
def ExportUserdata(a,m,obj,modelNode,includeCollectionTags=True,fOptions=None):
    print("EXPORT USERDATA")
    attribID = m
    a["{:d}".format(m)] = ET.SubElement(a[modelNode], "attribute")
    a["{:d}".format(m)].set("name", "Variables")
    m += 1

    tags = []

    def add_userdata(key,value,type="String"):
        nonlocal m,a
        a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(attribID)], "variant")
        a["{:d}".format(m)].set("hash", str(SDBMHash(key)))
        a["{:d}".format(m)].set("type", type)
        a["{:d}".format(m)].set("value", value)
        m += 1

    for ud in obj.user_data:
        if ud.key.lower() != "tag":
            add_userdata(ud.key,ud.value)
        else:
            tags.extend(ud.value.split(","))

    animation_object = None

    node_animation = False


    if obj.parent and obj.parent.type=="ARMATURE" and obj.parent.animation_data:
        animation_object = obj.parent
    elif obj and obj.animation_data:
        animation_object = obj
        node_animation = True


    if animation_object:
        animdata = animation_object.animation_data
        
        if animdata.action:
            action_name=animdata.action.name

            filepath = GetFilepath(PathType.ANIMATIONS, action_name, fOptions)
            animation_filename = filepath[1]
            if node_animation:
                add_userdata("__runtime_nodeanimation",animation_filename)
                tags.append("__runtime_nodeanim")
            else:
                add_userdata("__runtime_animation",animation_filename)

            current_time =  (bpy.context.scene.frame_current-1) / bpy.context.scene.render.fps
            add_userdata("__runtime_animation_time",str(current_time),"Float")

    if obj.type=="MESH" and obj.data.shape_keys:
        result = ""
        first=True
        for block in obj.data.shape_keys.key_blocks:
            if first or block.mute or block.value==0:
                first=False
                continue
            
            if result!="":
                result+="|"
            result+="%s~%s" %(block.name,block.value)

        if result!="":
            add_userdata("__runtime_shapekeys",result)


    if includeCollectionTags:
        print("INCLUDE COLTAGS")
        collectionTags = GetCollectionTags(obj)
        for colTag in collectionTags:
            print("TAG:"+colTag)
            tags.append(colTag)


    if tags:
        tagsID = m
        a["{:d}".format(tagsID)] = ET.SubElement(a[modelNode], "attribute")
        a["{:d}".format(tagsID)].set("name", "Tags")
        m += 1
        for tag in tags:
            a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(tagsID)], "string")
            a["{:d}".format(m)].set("value", tag.strip())
            m += 1


            

    return m

# look up userdata in the specific object with the given key. return None if not present
def GetUserData(obj,key):
    for kv in obj.user_data:
        if kv.key==key:
            return kv
    return None

# find tag with value 
def HasTag(obj,tagName):
    for kv in obj.user_data:
        if kv.key=="tag" and kv.value==tagName:
            return True
    return False

def ProcessNodetreeMaterials(mesh):
    result = []
    for nt in mesh.materialNodetrees:
        if nt.nodetreePointer:
            ntResult = ProcessNodetreeMaterial(mesh,nt.nodetreePointer)
            result.append(ntResult)
        else:
            result.append(None)
    return result

def ProcessNodetreeMaterial(mesh,materialNT):
    # search for predef-material-node and use the material it defines
    for node in materialNT.nodes:
        if node.bl_idname=="urho3dmaterials__predefMaterialNode":
            return node.prop_Material
    
    # add this material-nodetree in the list of used materialtrees for later export
    if materialNT not in usedMaterialTrees:
        usedMaterialTrees.append(materialNT)

    # no predef. use the material created by this nodetree
    return "Materials/"+materialNT.name+".xml"

## this functions is used to fill the usedMaterialTrees-array without the whole export-process
## and is needed for "Export Materials only"
def SetUsedMaterials():
    for mesh in bpy.data.meshes:
        ProcessNodetreeMaterials(mesh)
    print("UsedMaterials:%s" % usedMaterialTrees)


# get all tags of the direct collections and the collections in which it is nested in (postfix: _recursive )
def GetCollectionTags(obj):
    result = []
    for col in bpy.data.collections:
        if obj.name in col.objects:
            result.append(col.name)
        if obj.name in col.all_objects:
            result.append(col.name+"_recursive")
    return result

def GetXMLComponent(a,name):
    for comp in a:
        print(comp.tag)
        if comp.tag=="component" and comp.get("type")==name:
            return comp
    return None

def HasComponent(a,name):
    return GetXMLComponent(a,name) != None    

# Export scene and nodes
def UrhoExportScene(context, uScene, sOptions, fOptions):
    usedMaterialTrees.clear()

    blenderScene = bpy.data.scenes[uScene.blenderSceneName]
    urho_settings = blenderScene.urho_exportsettings
    '''
    # Re-order meshes
    orderedModelsList = []
    for obj in blenderScene.objects:
        if obj.type == 'MESH':
            for uSceneModel in uScene.modelsList:
                if uSceneModel.objectName == obj.name:
                    orderedModelsList.append(uSceneModel)
    uScene.modelsList = orderedModelsList
    '''

    fileid = bpy.data.worlds[0].global_settings.file_id
    scene_hash = SDBMHash(bpy.context.scene.name)%100

    k = fileid * 1000000 + scene_hash * 10000


    a = {}
    #k = 0x1000000   # node ID
    compoID = k     # component ID
    m = 0           # internal counter

    def add_attributes(parent,attributes=[]):
        nonlocal m

        for key in attributes:
            a["{:d}".format(m)] = ET.SubElement(parent, "attribute")
            a["{:d}".format(m)].set("name", str(key))
            a["{:d}".format(m)].set("value", str(attributes[key]))
            m += 1

    def add_component(parent,componentType,attributes=[]):
        nonlocal compoID
        nonlocal m
        
        compoID += 1 

        a["{:d}".format(compoID)] = ET.SubElement(parent, "component")
        a["{:d}".format(compoID)]
        a["{:d}".format(compoID)].set("type", componentType)
        a["{:d}".format(compoID)].set("id", "{:d}".format(compoID))
        m += 1

        for key in attributes:
            a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(compoID)], "attribute")
            a["{:d}".format(m)].set("name", str(key))
            a["{:d}".format(m)].set("value", str(attributes[key]))
            m += 1
        compoID += 1

    if urho_settings.generateSceneHeader:
        header_data,header_objects = PrepareSceneHeaderFile(bpy.context.scene)
        global_header_data = PrepareGlobalHeader()
    

    # Create scene components
    if sOptions.doScenePrefab:
        sceneRoot = ET.Element('scene')
        sceneRoot.set("id", "1")

        add_component(sceneRoot,"Octree")
        add_component(sceneRoot,"DebugRenderer")
        if not sOptions.noPhysics:
            a["{:d}".format(m)] = ET.SubElement(sceneRoot, "component")
            a["{:d}".format(m)].set("type", "PhysicsWorld")
            a["{:d}".format(m)].set("id", "4")
            m += 1

        # Create Root node
        root = ET.SubElement(sceneRoot, "node")
    else: 
        # Root node
        root = ET.Element('node') 

    root.set("id", "{:d}".format(k))
    a["{:d}".format(m)] = ET.SubElement(root, "attribute")
    a["{:d}".format(m)].set("name", "Name")
    a["{:d}".format(m)].set("value", uScene.blenderSceneName)

    foundSceneNodeTree = False
    try:
#            print("SCENETREE CHECK: %s %s %s" % ( jsonNodetreeAvailable, str(blenderScene.nodetree is not None), blenderScene.nodetree.name)) 
        if jsonNodetreeAvailable and blenderScene.nodetree:
            # bypass nodeID and receive the new value
            print("FOUND SCENE")
            compoID = CreateNodeTreeXML(root,blenderScene.nodetree,compoID)
            foundSceneNodeTree = True
    except Exception as e:
        log.error("Cannot export scene nodetree {:s} " % str(e) )
        log.critical("Couldn't export scene-nodetree. skipping nodetree and going on with default behaviour")
        pass        


    if sOptions.SceneCreateZone:
        zone_attrs = {}
        zone_attrs["Bounding Box Min"]="-2000 -2000 -2000"
        zone_attrs["Bounding Box Max"]="2000 2000 2000"
        zone_attrs["Ambient Color"]="0.15 0.15 0.15 1"
        zone_attrs["Fog Color"]="0.5 0.5 0.7 1"
        zone_attrs["Fog Start"]=300
        zone_attrs["Fog End"]=500
        if sOptions.ZoneTexture and sOptions.ZoneTexture!="None":
            zone_attrs["Zone Texture"]=sOptions.ZoneTexture
        add_component(root,"Zone",zone_attrs)

    if urho_settings.sceneCreateSkybox and urho_settings.sceneSkyBoxCubeTexture:
        skybox = a["__skybox"] = ET.SubElement(root, "node")
        
        # <attribute name="Is Enabled" value="true" />
		# <attribute name="Name" value="Sky" />
		# <attribute name="Tags" />
		# <attribute name="Position" value="0 0 0" />
		# <attribute name="Rotation" value="1 0 0 0" />
		# <attribute name="Scale" value="1 1 1" />
		# <attribute name="Variables" />
        attrs={}
        attrs["Is Enabled"]=True
        attrs["Name"]="%sSkybox" % context.scene.name
        add_attributes(skybox,attrs)

        # <component type="Skybox" id="12">
        # <component type="Skybox" id="12">
		# 	<attribute name="Model" value="Model;Models/Sphere.mdl" />
		# 	<attribute name="Material" value="Material;Materials/Skybox2.xml" />
		# </component>
        skybox_attrs = {}
        skybox_attrs["Model"]="Model;Models/SkyboxSphere.mdl"
        materialName = "Materials/_%s_Skybox.xml" % context.scene.name
        skybox_attrs["Material"]="Material;%s" % materialName
        add_component(skybox,"Skybox",skybox_attrs)            

        _skyboxTechnique="DiffSkybox"
        if urho_settings.sceneSkyBoxHDR:
            _skyboxTechnique += "HDRScale"

        skyboxMaterial="""
<material>
	<parameter name="MatDiffColor" value="1 1 1 1"/>
	<parameter name="MatSpecColor" value="0 0 0 1"/>
	<parameter name="MatEmissiveColor" value="0 0 0"/>
	<parameter name="UOffset" value="1.0 0 0 0"/>
	<parameter name="VOffset" value="0 1.0 0 0"/>
	<texture name="%s" unit="diffuse"/>
	<cull value="none"/>
	<shadowcull value="ccw"/>
	<fill value="solid"/>
	<technique loddistance="0" name="Techniques/%s.xml" quality="0"/>
</material>
            """ % (urho_settings.sceneSkyBoxCubeTexture,_skyboxTechnique)
        matPath = GetFilepath(PathType.MATERIALS, "_%s_Skybox"% context.scene.name, fOptions)
        WriteStringFile(skyboxMaterial,matPath[0],fOptions)

  #  a["lightnode"] = ET.SubElement(root, "node")

  #  a["{:d}".format(m+2)] = ET.SubElement(a["lightnode"], "component")
   # a["{:d}".format(m+2)].set("type", "Light")
    #a["{:d}".format(m+2)].set("id", "3")

#    a["{:d}".format(m+3)] = ET.SubElement(a["{:d}".format(m+2)], "attribute")
#    a["{:d}".format(m+3)].set("name", "Light Type")
#    a["{:d}".format(m+3)].set("value", "Directional")

#    a["{:d}".format(m+4)] = ET.SubElement(a["lightnode"], "attribute")
#    a["{:d}".format(m+4)].set("name", "Rotation")
#    a["{:d}".format(m+4)].set("value", "0.884784 0.399593 0.239756 -0")

    attrs={
        "RenderPath" : urho_settings.runtimeRenderPath,
        "HDR" : urho_settings.runtimeUseHDR,
        "Gamma" : urho_settings.runtimeUseGamma,
        "Bloom" : urho_settings.runtimeUseBloom,
        "FXAA2" : urho_settings.runtimeUseFXAA2,
        "sRGB" : urho_settings.runtimeShowSRGB
    }
    add_component(root,"RenderData",attrs)


    # Create physics stuff for the root node
    if sOptions.globalPhysics:
        a["{:d}".format(m)] = ET.SubElement(root, "component")
        a["{:d}".format(m)].set("type", "RigidBody")
        a["{:d}".format(m)].set("id", "{:d}".format(compoID))

        a["{:d}".format(m+1)] = ET.SubElement(a["{:d}".format(m)] , "attribute")
        a["{:d}".format(m+1)].set("name", "Collision Layer")
        a["{:d}".format(m+1)].set("value", "2")

        a["{:d}".format(m+2)] = ET.SubElement(a["{:d}".format(m)], "attribute")
        a["{:d}".format(m+2)].set("name", "Use Gravity")
        a["{:d}".format(m+2)].set("value", "false")

        a["{:d}".format(m+3)] = ET.SubElement(root, "component")
        a["{:d}".format(m+3)].set("type", "CollisionShape")
        a["{:d}".format(m+3)].set("id", "{:d}".format(compoID+1))
        m += 3

        a["{:d}".format(m+1)] = ET.SubElement(a["{:d}".format(m)], "attribute")
        a["{:d}".format(m+1)].set("name", "Shape Type")
        a["{:d}".format(m+1)].set("value", "TriangleMesh")

        physicsModelFile = GetFilepath(PathType.MODELS, "Physics", fOptions)[1]
        a["{:d}".format(m+2)] = ET.SubElement(a["{:d}".format(m)], "attribute")
        a["{:d}".format(m+2)].set("name", "Model")
        a["{:d}".format(m+2)].set("value", "Model;" + physicsModelFile)
        m += 2
        compoID += 2

    if sOptions.trasfObjects and sOptions.globalOrigin:
        log.warning("To export objects transformations you should use Origin = Local")

    # Sort the models by parent-child relationship
    uScene.SortModels()

    # save the parent objects
    parentObjects = []

    # what object in what collection
    groupObjMapping = {}
    # list to contain xml-data for each collection to be exported
    groups=[]
    # list of collections that get instanced in the scene
    instancedCollections = []


    # Export each decomposed object
    def ObjInGroup(obj):
        return obj.name in groupObjMapping
    def GetGroupName(grpName):
        return "col_"+grpName    


    # add all collections that are marked as "export as urho object" to the export-collection list
    print("COLLECTION-Handling:")
    for col in bpy.data.collections:
        print("Check collection %s" % col.name)
        if col.library:
            print("Ignoring linked collection:%s",col.name)
            continue

        if col.urhoExport:
            if not col in instancedCollections:
                print("Export collection:%s" % col.name)
                instancedCollections.append(col)            

    if sOptions.exportGroupsAsObject:
        # find all instanced collections
        for obj in bpy.context.scene.objects:
            if obj.instance_type=="COLLECTION":
                # found an instanced collection
                collection = obj.instance_collection
                
                if collection.library:
                    print("ignoring linked collection: %s" % collection.name)
                    continue
                
                if not collection in instancedCollections:
                    instancedCollections.append(collection)

    ## create a mapping to determine in which collection the corressponding object is contained
    for col in instancedCollections:
        grpObjects = col.all_objects[:] 
        for grpObj in grpObjects:
            print(("obj:%s grp:%s") %(grpObj.name,col.name) )

            if grpObj.type=="ARMATURE":
                print("Found armature: adding children to group")
                for child in grpObj.children:
                    if child not in grpObjects:
                        grpObjects.append(child)
                        print("armature-child:%s" % child.name)
                continue

            if grpObj.name in groupObjMapping:
                groupObjMapping[grpObj.name].append(col)
                #log.critical("Object:{:s} is in multiple collections! Only one collection per object is supported, atm! Using grp:{:s} ".format(grpObj.name, groupObjMapping[grpObj.name]) )
            else:
                groupObjMapping[grpObj.name]=[col]

        
    for uSceneModel in uScene.modelsList:
        modelNode = uSceneModel.name
        log.info ("Process %s" % modelNode)
        isEmpty = False
        obj = None
        try:
            obj = bpy.data.objects[modelNode]

            if obj.type=="ARMATURE":
                continue

            isEmpty = obj.type=="EMPTY" or obj.type=="CAMERA" or obj.type=="LIGHT" or (sOptions.wiredAsEmpty and obj.display_type=="WIRE") 
        except:
            pass

        if not obj:
            print("Skipping non-object:%s" % modelNode)
            continue

        print("Process:%s Type:%s IsEmpty:%s DrawType:%s" % (obj.name,obj.type,isEmpty,obj.display_type) )

        modelFile = None
        materials = None
        if not isEmpty:
            # Get model file relative path
            modelFile = uScene.FindFile(PathType.MODELS, modelNode)
            # Gather materials
            materials = ""
            if jsonNodetreeAvailable and obj.data.materialNodetrees:
                # create materials
                procMaterials = ProcessNodetreeMaterials(obj.data)
                # interate over result-names
                for pMat in procMaterials:
                    if pMat:
                        materials += ";"+pMat
                    else:
                        materials += ";Materials/DefaultGrey.xml"
            
            if materials == "": # not processed via materialnodes,yet? use the default way
                for uSceneMaterial in uSceneModel.materialsList:
                    file = uScene.FindFile(PathType.MATERIALS, uSceneMaterial.name)
                    materials += ";" + file
        # elif sOptions.exportGroupsAsObject:
        #     if obj.dupli_type == 'GROUP':
        #         grp = obj.dupli_group
        #         # check if we already have a group__ element in which we store the filename of the group
        #         ud = GetUserData(obj,"group__")
        #         if not ud:
        #             ud = obj.user_data.add()
        #             ud.key="group__"
        #         ud.value = sOptions.objectsPath+"/"+GetGroupName(grp.name)+".xml"
                
        #         if not HasTag(obj,"groupInstance__"):
        #             tag = obj.user_data.add()
        #             tag.key="tag"
        #             tag.value="groupInstance__"
                

        # Generate XML Content
        k += 1
        
        # if in export only selected mode make sure those selections are put as root object
        add_exception = obj.parent and urho_settings.source=="ONLY_SELECTED" and obj.parent not in bpy.context.selected_objects

        # Parenting: make sure parented objects are child of this in xml as well
        print ( ("PARENT:%s type:%s") % (str(uSceneModel.parentObjectName),str(uSceneModel.type)))
        if not add_exception and not isEmpty and uSceneModel.parentObjectName and (uSceneModel.parentObjectName in a):
            for usm in uScene.modelsList:
                if usm.name == uSceneModel.parentObjectName:
                    a[modelNode] = ET.SubElement(a[usm.name], "node")
                    break
        else:
            if not uSceneModel.parentObjectName or add_exception:
                a[modelNode] = ET.SubElement(root, "node")
                parentObjects.append({'xml':a[modelNode],'uSceneModel':uSceneModel})
            else:
                for usm in uScene.modelsList:
                    if usm.name == uSceneModel.parentObjectName:
                        print("name:%s parentName:%s" % ( uSceneModel.objectName,uSceneModel.parentObjectName ))
                        a[modelNode] = ET.SubElement(a[usm.name], "node")
                        break                    

            if ObjInGroup(obj):
                print("FOUND GROUP OBJ:%s",obj.name)
                
                for group in groupObjMapping[obj.name]:
                    groupName = GetGroupName(group.name)
                    
                    # get or create node for the group
                    if  groupName not in a :
                        offset = group.instance_offset # Vector((0,0,0)) # no offset in blender 2.8 anymore

                        a[groupName] = ET.Element('node')
                        # a["{:d}".format(m)] = ET.SubElement(a[groupName], "attribute")
                        # a["{:d}".format(m)].set("name", "Position")
                        # a["{:d}".format(m)].set("value", "%s %s %s" % ( offset.y,-offset.z, -offset.x ) )
                        # m += 1

                        
                        # apply group offset
                        #offset = group.dupli_offset
                        
                        offset = group.instance_offset # Vector((0,0,0)) # no offset in blender 2.8 anymore
                        modelPos = uSceneModel.position
                        ## CAUTION/TODO: this only works for default front-view (I guess)
                        print("POSITION %s : offset %s" % ( modelPos,offset ))
                        colInstPos = Vector( (modelPos.x + offset.y, modelPos.y - offset.z, modelPos.z - offset.x) )
                        print("NEW Collection Instance POS %s: " % ( colInstPos ))
                        uSceneModel.colInstPosition = colInstPos

                        groups.append({'xml':a[groupName],'obj':obj,'group':group, 'instance_offset_delta' : (offset.y,-offset.z,-offset.x) })
                    
                    # create root for the group object
                    print("a[%s].append(a[%s]" %(groupName,modelNode))
                    if modelNode in a and a[modelNode] not in a[groupName]:
                        a[groupName].append(a[modelNode])
                #a[modelNode] = ET.SubElement(a[groupName],'node') 

        a[modelNode].set("id", "{:d}".format(k))
        
        if urho_settings.generateSceneHeader:
            header_obj_data = header_objects[obj]
            header_obj_data["id"]=k

        a["{:d}".format(m)] = ET.SubElement(a[modelNode], "attribute")
        a["{:d}".format(m)].set("name", "Name")
        a["{:d}".format(m)].set("value", uSceneModel.name)
        m += 1

        if sOptions.trasfObjects:
            a["{:d}".format(m)] = ET.SubElement(a[modelNode], "attribute")
            a["{:d}".format(m)].set("name", "Position")
            a["{:d}".format(m)].set("value", Vector3ToString(uSceneModel.position))
            m += 1
            a["{:d}".format(m)] = ET.SubElement(a[modelNode], "attribute")
            a["{:d}".format(m)].set("name", "Rotation")
            a["{:d}".format(m)].set("value", Vector4ToString(uSceneModel.rotation))
            m += 1
            a["{:d}".format(m)] = ET.SubElement(a[modelNode], "attribute")
            a["{:d}".format(m)].set("name", "Scale")
            a["{:d}".format(m)].set("value", Vector3ToString(uSceneModel.scale))
            m += 1
        
        if (sOptions.exportUserdata or sOptions.exportObjectCollectionAsTag) and obj:
            m = ExportUserdata(a,m,obj,modelNode,sOptions.exportObjectCollectionAsTag,fOptions)
        
        if sOptions.exportGroupsAsObject and obj.instance_type == 'COLLECTION':
            grp = obj.instance_collection
            grpFilename = sOptions.objectsPath+"/"+GetGroupName(grp.name)+".xml"
            m = AddGroupInstanceComponent(a,m,grpFilename,grp.instance_offset,modelNode)

        xmlCurrentModelNode = None

        if not isEmpty:
            compID = m
            a["{:d}".format(compID)] = ET.SubElement(a[modelNode], "component")
            xmlCurrentModelNode = a["{:d}".format(compID)]
            a["{:d}".format(compID)].set("type", uSceneModel.type)
            a["{:d}".format(compID)].set("id", "{:d}".format(compoID))
            m += 1

            a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(compID)], "attribute")
            a["{:d}".format(m)].set("name", "Model")
            currentModel = "Model;" + modelFile
            
            a["{:d}".format(m)].set("value", currentModel)
            m += 1

            if obj.hide_render:
                a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(compID)], "attribute")
                a["{:d}".format(m)].set("name", "Is Enabled")
                a["{:d}".format(m)].set("value", "false")
                m += 1


            a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(compID)], "attribute")
            a["{:d}".format(m)].set("name", "Material")
            currentMaterialValue = "Material" + materials
            a["{:d}".format(m)].set("value", currentMaterialValue)
            m += 1

            if obj.parent_type=="BONE":
                attrs={
                    "boneName" : obj.parent_bone
                }
                add_component(a[modelNode],"ParentBone",attrs)


            if obj.type=="MESH":
                if obj.cast_shadow:
                    a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(compID)], "attribute")
                    a["{:d}".format(m)].set("name", "Cast Shadows")
                    a["{:d}".format(m)].set("value", "true")
                    m += 1
                else:
                    a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(compID)], "attribute")
                    a["{:d}".format(m)].set("name", "Cast Shadows")
                    a["{:d}".format(m)].set("value", "false")
                    m += 1


                # if obj.receive_shadow:
                #     a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(compID)], "attribute")
                #     a["{:d}".format(m)].set("name", "Shadow Mask")
                #     a["{:d}".format(m)].set("value", "1")
                #     m += 1                           
                # else:
                #     a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(compID)], "attribute")
                #     a["{:d}".format(m)].set("name", "Shadow Mask")
                #     a["{:d}".format(m)].set("value", "0")
                #     m += 1                           

            compoID += 1

            finishedNodeTree = False
            try:
                if jsonNodetreeAvailable:
                    # keep track of already exported nodetrees to prevent one nodetree added multiple times
                    # TODO: prevent inconsistend data in the first place
                    handledNodetrees = []
                    
                    # merge the nodetress on the armature on the mesh-object
                    if obj.parent and obj.parent.type=="ARMATURE": 
                        for nodetreeSlot in obj.parent.nodetrees:
                            nt = nodetreeSlot.nodetreePointer
                            if (nt not in handledNodetrees):
                                compoID = CreateNodeTreeXML(a[modelNode],nt,compoID,currentModel,currentMaterialValue,xmlCurrentModelNode,modelNode)
                                handledNodetrees.append(nt)
                            else:
                                # we already added this nodetree! nothing more to do
                                pass


                    for nodetreeSlot in obj.nodetrees:
                        nt = nodetreeSlot.nodetreePointer
                        if (nt not in handledNodetrees):
                            compoID = CreateNodeTreeXML(a[modelNode],nt,compoID,currentModel,currentMaterialValue,xmlCurrentModelNode,modelNode)
                            handledNodetrees.append(nt)
                        else:
                            # we already added this nodetree! nothing more to do
                            pass
                    finishedNodeTree = True
            except:
                desired_trace = traceback.format_exc()
                print("Unexpected error in jsonnodetree_register:", desired_trace)                
                log.critical("Couldn't export nodetree. skipping nodetree and going on with default behaviour")
                pass

            if not finishedNodeTree:
                # the default-behaviour
                if sOptions.individualPhysics:
                    #Use model's bounding box to compute CollisionShape's size and offset
                    physicsSettings = [sOptions.shape] #tData.physicsSettings = [sOptions.shape, obj.game.physics_type, obj.game.mass, obj.game.radius, obj.game.velocity_min, obj.game.velocity_max, obj.game.collision_group, obj.game.collision_mask, obj.game.use_ghost] **************************************
                    shapeType = physicsSettings[0]
                    if not sOptions.mergeObjects and obj.game.use_collision_bounds:
                        for shapeItems in sOptions.shapeItems:
                            if shapeItems[0] == obj.game.collision_bounds_type:
                                shapeType = shapeItems[1]
                                break
                    bbox = uSceneModel.boundingBox
                    #Size
                    shapeSize = Vector()
                    if bbox.min and bbox.max:
                        shapeSize.x = bbox.max[0] - bbox.min[0]
                        shapeSize.y = bbox.max[1] - bbox.min[1]
                        shapeSize.z = bbox.max[2] - bbox.min[2]
                    #Offset
                    shapeOffset = Vector()
                    if bbox.max:
                        shapeOffset.x = bbox.max[0] - shapeSize.x / 2
                        shapeOffset.y = bbox.max[1] - shapeSize.y / 2
                        shapeOffset.z = bbox.max[2] - shapeSize.z / 2

                    a["{:d}".format(m)] = ET.SubElement(a[modelNode], "component")
                    a["{:d}".format(m)].set("type", "RigidBody")
                    a["{:d}".format(m)].set("id", "{:d}".format(compoID))
                    m += 1

                    a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(m-1)], "attribute")
                    a["{:d}".format(m)].set("name", "Collision Layer")
                    a["{:d}".format(m)].set("value", "2")
                    m += 1

                    a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(m-2)], "attribute")
                    a["{:d}".format(m)].set("name", "Use Gravity")
                    a["{:d}".format(m)].set("value", "false")
                    m += 1

                    a["{:d}".format(m)] = ET.SubElement(a[modelNode], "component")
                    a["{:d}".format(m)].set("type", "CollisionShape")
                    a["{:d}".format(m)].set("id", "{:d}".format(compoID+1))
                    m += 1

                    a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(m-1)] , "attribute")
                    a["{:d}".format(m)].set("name", "Shape Type")
                    a["{:d}".format(m)].set("value", shapeType)
                    m += 1

                    if shapeType == "TriangleMesh":
                        a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(m-2)], "attribute")
                        a["{:d}".format(m)].set("name", "Model")
                        a["{:d}".format(m)].set("value", "Model;" + modelFile)

                    else:
                        a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(m-2)] , "attribute")
                        a["{:d}".format(m)].set("name", "Size")
                        a["{:d}".format(m)].set("value", Vector3ToString(shapeSize))
                        m += 1

                        a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(m-3)] , "attribute")
                        a["{:d}".format(m)].set("name", "Offset Position")
                        a["{:d}".format(m)].set("value", Vector3ToString(shapeOffset))
                        m += 1

                    compoID += 2
        else:
            if jsonNodetreeAvailable and hasattr(obj,"nodetrees") and len(obj.nodetrees)>0:
                handledNodetrees = []
                
                for nodetreeSlot in obj.nodetrees:
                    nt = nodetreeSlot.nodetreePointer
                    if (nt and nt not in handledNodetrees):
                        compoID = CreateNodeTreeXML(a[modelNode],nt,compoID)
                        handledNodetrees.append(id)
                    else:
                        # we already added this nodetree! nothing more to do
                        pass

            if obj.parent_type=="BONE":
                attrs={
                    "boneName" : obj.parent_bone
                }
                add_component(a[modelNode],"ParentBone",attrs)

            if obj.type == "LIGHT": #simple shadow-settings-export. For more control use LightNode
                if not HasComponent(a[modelNode],"RotationFix"):
                    add_component(a[modelNode],"RotationFix")

                # check if
                if not HasComponent(a[modelNode],"Light"):
                    ldata = obj.data
                    light_attrs={}
                    light_attrs["Is Enabled"]="true"
                    light_attrs["Use Physical Values"]=ldata.use_pbr
                    
                    light_attrs["Brightness Multiplier"]=ldata.energy

                    if ldata.type=="POINT":
                        light_attrs["Light Type"] = "Point"
                        light_attrs["Range"] = ldata.shadow_soft_size
                    elif ldata.type=="SUN" or ldata.type=="AREA":                
                        light_attrs["Light Type"] = "Directional"
                        light_attrs["Specular Intensity"]=ldata.specular_factor
                    elif ldata.type=="SPOT":                
                        light_attrs["Light Type"] = "Spot"
                        light_attrs["Range"] = ldata.shadow_soft_size
                        light_attrs["Spot FOV"]=math.degrees(ldata.spot_size)
                        
                    col = ldata.color
                    light_attrs["Color"]="%s %s %s 1" % (col.r,col.g,col.b)

                    try:
                        if ldata.cycles.cast_shadow:
                            light_attrs["Cast Shadows"]="true"
                        else:
                            light_attrs["Cast Shadows"]="false"
                    except:
                        print("could not determin cast-shadow-value => false")
                        light_attrs["Cast Shadows"]="false"

                    add_component(a[modelNode],"Light",light_attrs)


                    
            # export camera
            if obj.type == "CAMERA":
                if not HasComponent(a[modelNode],"RotationFix"):
                    add_component(a[modelNode],"RotationFix")

                # check if there is a camera-component already (created by nodetree)
                if HasComponent(a[modelNode],"Camera"):
                    print("There is a camera-node => ignore camera-object-data")
                else:                    
                    blender_cam = obj.data

                    # compID = m
                    # a["{:d}".format(compID)] = ET.SubElement(a[modelNode], "component")
                    # xmlCurrentModelNode = a["{:d}".format(compID)]
                    # a["{:d}".format(compID)].set("type", "Camera")
                    # a["{:d}".format(compID)].set("id", "{:d}".format(compoID))
                    # m += 1

                    camera_data = {}
                    if blender_cam.type=="PERSP":
                        camera_data["Orthographic"]="false"
                        camera_data["FOV"]=math.degrees(blender_cam.angle)
                    else:
                        camera_data["Orthographic"]="true"
                        camera_data["Orthographic Size"]=blender_cam.ortho_scale

                    camera_data["Near Clip"]=blender_cam.clip_start
                    camera_data["Far Clip"]=blender_cam.clip_end


                    add_component(a[modelNode],"Camera",camera_data);


                    # for key in camera_data:
                    #     a["{:d}".format(m)] = ET.SubElement(a["{:d}".format(compID)], "attribute")
                    #     a["{:d}".format(m)].set("name", str(key))
                    #     a["{:d}".format(m)].set("value", str(camera_data[key]))
                    #     m += 1


                    # compoID += 1


        # Write individual prefabs
        if sOptions.doIndividualPrefab and not sOptions.individualPrefab_onlyRootObject:
            filepath = GetFilepath(PathType.OBJECTS, uSceneModel.name, fOptions)
            if CheckFilepath(filepath[0], fOptions):
                log.info( "Creating prefab {:s}".format(filepath[1]) )
                WriteXmlFile(a[modelNode], filepath[0], fOptions)

        # Merging objects equates to an individual export. And collective equates to individual, so we can skip collective
        if sOptions.mergeObjects and sOptions.doScenePrefab: 
            filepath = GetFilepath(PathType.SCENES, uScene.blenderSceneName, fOptions)
            if CheckFilepath(filepath[0], fOptions):
                log.info( "Creating scene prefab {:s}".format(filepath[1]) )
                WriteXmlFile(sceneRoot, filepath[0], fOptions)

    # Write individual prefabs
    if sOptions.doIndividualPrefab:
        if sOptions.individualPrefab_onlyRootObject:
            for model in parentObjects:
                filepath = GetFilepath(PathType.OBJECTS, model["uSceneModel"].name, fOptions)
                if CheckFilepath(filepath[0], fOptions):
                    log.info( "!!Creating prefab {:s}".format(filepath[1]) )
                    WriteXmlFile(model["xml"], filepath[0], fOptions)

    if (sOptions.exportGroupsAsObject):
        for grp in groups:
            filepath = GetFilepath(PathType.OBJECTS, GetGroupName(grp["group"].name), fOptions)
            if CheckFilepath(filepath[0], fOptions):
                log.info( "!!Creating group-prefab {:s}".format(filepath[1]) )
                dx,dy,dz=grp["instance_offset_delta"]
                clone_data = copy.deepcopy(grp["xml"])
                #rewrite positions of root-objects inside collection according to the collection-offset
                for data in clone_data:
                    print(data)
                    if data.tag=="node":
                        for idata in data:
                            if idata.tag=="attribute" and idata.attrib["name"]=="Position":
                                value = idata.attrib["value"]
                                x,y,z=value.split(' ')
                                
                                new_x = float(x) + float(dx);   
                                new_y = float(y) + float(dy);   
                                new_z = float(z) + float(dz);   

                                idata.attrib["value"]="%s %s %s" % (new_x,new_y,new_z)

                WriteXmlFile(clone_data, filepath[0], fOptions)

    # Write collective and scene prefab files
    if not sOptions.mergeObjects:

        if sOptions.doCollectivePrefab:
            filepath = GetFilepath(PathType.OBJECTS, uScene.blenderSceneName, fOptions)
            if CheckFilepath(filepath[0], fOptions):
                log.info( "Creating collective prefab {:s}".format(filepath[1]) )
                WriteXmlFile(root, filepath[0], fOptions)

        if sOptions.doScenePrefab:
            filepath = GetFilepath(PathType.SCENES, uScene.blenderSceneName, fOptions)
            if CheckFilepath(filepath[0], fOptions):
                log.info( "Creating scene prefab {:s}".format(filepath[1]) )
                WriteXmlFile(sceneRoot, filepath[0], fOptions)

            print("START EXPORTING MATERIALNODETREES")
            print("FILEPATH %s" % filepath[0])
            
            log.info( "Creating material {:s}".format(filepath[1]) )
            
            UrhoWriteMaterialTrees(fOptions)         
    
    if urho_settings.generateSceneHeader:
        WriteSceneHeaderFile("scenes",header_data,os.path.join(bpy.path.abspath(urho_settings.sceneHeaderOutputPath),"")+("%s.h"%bpy.context.scene.name))
        WriteSceneHeaderFile("global",global_header_data,os.path.join(bpy.path.abspath(urho_settings.sceneHeaderOutputPath),"")+("global_resources.h"))
           

            

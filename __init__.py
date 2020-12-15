
# LOD: be sure all have the same material or a new geometry is created

#
# This script is licensed as public domain.
#

# http://www.blender.org/documentation/blender_python_api_2_57_release/bpy.props.html
# http://www.blender.org/documentation/blender_python_api_2_59_0/bpy.props.html
# http://www.blender.org/documentation/blender_python_api_2_66_4/bpy.props.html
# http://www.blender.org/documentation/blender_python_api_2_57_release/bpy.types.Panel.html
# http://www.blender.org/documentation/blender_python_api_2_57_release/bpy.types.PropertyGroup.html
# http://www.blender.org/documentation/blender_python_api_2_66_4/bpy.types.WindowManager.html
# http://wiki.blender.org/index.php/Dev:2.5/Py/Scripts/Guidelines/Layouts
# http://wiki.blender.org/index.php/Dev:2.5/Py/Scripts/Cookbook/Code_snippets/Properties
# http://wiki.blender.org/index.php/Dev:2.5/Py/Scripts/Cookbook/Code_snippets/Interface
# http://wiki.blender.org/index.php/Dev:IT/2.5/Py/Scripts/Cookbook/Code_snippets/Interface
# http://wiki.blender.org/index.php/Dev:IT/2.5/Py/Scripts/Cookbook/Code_snippets/Multi-File_packages
# http://wiki.blender.org/index.php/Doc:2.6/Manual/Extensions/Python/Properties
# http://www.blender.org/documentation/blender_python_api_2_66_4/info_tutorial_addon.html

DEBUG = 0
if DEBUG: print("Urho export init")

bl_info = {
    "name": "Urho3D export",
    "description": "Urho3D export",
    "author": "reattiva, dertom",
    "version": (0, 8, 1),
    "blender": (2, 80, 0),
    "location": "Properties > Render > Urho export",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export"}

if "decompose" in locals():
    import imp
    imp.reload(decompose)
    imp.reload(export_urho)
    imp.reload(export_scene)
    imp.reload(utils)
    if DEBUG and "testing" in locals(): imp.reload(testing)

try:
    from PIL import Image,ImageDraw
except:
    import bpy,subprocess
    pybin = bpy.app.binary_path_python
    subprocess.check_call([pybin, '-m', 'ensurepip'])
    subprocess.check_call([pybin, '-m', 'pip', 'install', 'Pillow'])
    from PIL import Image,ImageDraw

import re
from pathlib import Path
from .decompose import TOptions, Scan
from .export_urho import UrhoExportData, UrhoExportOptions, UrhoWriteModel, UrhoWriteAnimation, \
                         UrhoWriteTriggers, UrhoExport
from .export_scene import SOptions, UrhoScene, UrhoExportScene, UrhoWriteMaterialTrees
from .utils import PathType, FOptions, GetFilepath, CheckFilepath, ErrorsMem, getLodSetWithID,getObjectWithID, execution_queue, \
                    PingData,set_found_blender_runtime,found_blender_runtime, PingForRuntime, copy_file,CalcNodeHash

from .networking import Start as StartNetwork
StartNetwork()

if DEBUG: from .testing import PrintUrhoData, PrintAll

from platform import system

from .custom_render_engine import UrhoRenderEngine,register as reRegister,unregister as reUnregister

# connect to blender connect if available
from .utils import vec2dict, matrix2dict

#import . addon_blender_connect
from .addon_blender_connect.BConnectNetwork import Publish,StartNetwork,NetworkRunning,AddListener,GetSessionId
from .addon_blender_connect import register as addon_blender_connect_register
from .addon_blender_connect import unregister as addon_blender_connect_unregister
import os,traceback
import time
import sys
import shutil
import logging, random, ntpath
import subprocess
import json
# object-array to keep track of temporary objects created just for the export-process(like for the lodsets)
tempObjects = []

from .addon_jsonnodetree import JSONNodetreeUtils   
from .addon_jsonnodetree.JSONNodetreeCustom import Custom 
from .addon_jsonnodetree import json_nodetree_register as jsonnodetree_register
from .addon_jsonnodetree import json_nodetree_unregister as jsonnodetree_unregister
from .addon_jsonnodetree import DeActivatePath2Timer as jsonnodetree_activateTimers
from .addon_jsonnodetree import drawJSONFileSettings as jsonnodetree_draw_ui
from .addon_jsonnodetree import NODE_PT_json_nodetree_file
from .addon_jsonnodetree import JSONNodetree

class URHO3D_JSONNODETREE_REBRAND(NODE_PT_json_nodetree_file):
    bl_category = "Urho3D"
    bl_label = "Urho3D-Settings"

import bpy
from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.app.handlers import persistent
from mathutils import Quaternion,Vector
from math import radians

#--------------------
# Loggers
#--------------------

# A list to save export messages
logList = []

# Create a logger
log = logging.getLogger("ExportLogger")
log.setLevel(logging.DEBUG)

# Formatter for the logger
FORMAT = '%(levelname)s:%(message)s'
formatter = logging.Formatter(FORMAT)

before_export_selection = None
before_export_mode = ""
before_export_active_obj = None


# Console filter: no more than 3 identical messages 
consoleFilterMsg = None
consoleFilterCount = 0
class ConsoleFilter(logging.Filter):
    def filter(self, record):
        global consoleFilterMsg
        global consoleFilterCount
        if consoleFilterMsg == record.msg:
            consoleFilterCount += 1
            if consoleFilterCount > 2:
                return False
        else:
            consoleFilterCount = 0
            consoleFilterMsg = record.msg
        return True
consoleFilter = ConsoleFilter()

# Logger handler which saves unique messages in the list
logMaxCount = 500
class ExportLoggerHandler(logging.StreamHandler):
    def emit(self, record):
        global logList
        try:
            if len(logList) < logMaxCount:
                msg = self.format(record)
                if not msg in logList:
                    logList.append(msg)
            #self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

# Delete old handlers
for handler in reversed(log.handlers):
    log.removeHandler(handler)

# Create a logger handler for the list
listHandler = ExportLoggerHandler()
listHandler.setFormatter(formatter)
log.addHandler(listHandler)
    
# Create a logger handler for the console
consoleHandler = logging.StreamHandler()
consoleHandler.addFilter(consoleFilter)
log.addHandler(consoleHandler)


def PublishAction(self,context,action,dataDict):
    setJson = json.dumps(dataDict, indent=4)
    data = str.encode(setJson)
    print("Publish action:%s data:%s" % (action,data))
    Publish("blender",action,"json",data)    



# publish runtime-settings (show_physics...) to runtime
def PublishRuntimeSettings(self,context):
    settings={}
    settings["export_path"]=bpy.path.abspath(self.outputPath)
    settings["show_physics"]=self.runtimeShowPhysics
    settings["show_physics_depth"]=self.runtimeShowPhysicsDepth
    settings["activate_physics"]=self.runtimeActivatePhysics
    settings["session_id"]=GetSessionId()
    if not self.runtimeExportComponents:
        settings["export_component_mode"]=0
    else:
        mode = self.runtimeExportComponentsMode
        if mode == "LITE":
            settings["export_component_mode"]=1
        elif mode == "ALL":
            settings["export_component_mode"]=2
        else:
            print("SETTINGS-ERROR! Unknown runtimeExportComponentsMode:%s" % mode)

    setJson = json.dumps(settings, indent=4)
    print("settingsJson: %s" % setJson)
    data = str.encode(setJson)

    Publish("blender","settings","json",data)


#    generateSceneHeader : BoolProperty(description="Export cpp-header to access scene-object name/id in code")

#    sceneHeaderOutputPath : StringProperty(


#--------------------
# Blender UI
#--------------------

current_system = system()
default_runtime_folder = ""
if current_system=="Linux":
    default_runtime_folder=os.path.dirname(os.path.realpath(__file__))+"/runtimes/urho3d-blender-runtime"
    if os.path.isfile(default_runtime_folder):
        os.chmod(default_runtime_folder, 0o755)

elif current_system=="Windows":
    default_runtime_folder=os.path.dirname(os.path.realpath(__file__))+"/runtimes/urho3d-blender-runtime.exe"


# Addon preferences, they are visible in the Users Preferences Addons page,
# under the Urho exporter addon row
class UrhoAddonPreferences(bpy.types.AddonPreferences):
    global default_runtime_folder

    bl_idname = __name__

    runtimeFile : bpy.props.StringProperty(
                name="Runtime",
                description="Path of the urho3d runtime",
                maxlen = 512,
                default = default_runtime_folder,
                subtype='FILE_PATH')

    outputPath : StringProperty(
            name = "Default export path",
            description = "Default path where to export",
            default = "", 
            maxlen = 1024,
            subtype = "DIR_PATH")

    modelsPath : StringProperty(
            name = "Default Models subpath",
            description = "Models subpath (relative to output)",
            default = "Models")
    animationsPath : StringProperty(
            name = "Default Animations subpath",
            description = "Animations subpath (relative to output)",
            default = "Models")
    materialsPath : StringProperty(
            name = "Default Materials subpath",
            description = "Materials subpath (relative to output)",
            default = "Materials")
    techniquesPath : StringProperty(
            name = "Default Techniques subpath",
            description = "Techniques subpath (relative to output)",
            default = "Techniques")
    texturesPath : StringProperty(
            name = "Default Textures subpath",
            description = "Textures subpath (relative to output)",
            default = "Textures")
    objectsPath : StringProperty(
            name = "Default Objects subpath",
            description = "Objects subpath (relative to output)",
            default = "Objects")
    scenesPath : StringProperty(
            name = "Default Scenes subpath",
            description = "Scenes subpath (relative to output)",
            default = "Scenes")

    bonesPerGeometry : IntProperty(
            name = "Per geometry",
            description = "Max numbers of bones per geometry",
            min = 64, max = 2048,
            default = 64)
    bonesPerVertex : IntProperty(
            name = "Per vertex",
            description = "Max numbers of bones per vertex",
            min = 4, max = 256,
            default = 4)

    reportWidth : IntProperty(
            name = "Window width",
            description = "Width of the report window",
            default = 500)

    maxMessagesCount : IntProperty(
            name = "Max number of messages",
            description = "Max number of messages in the report window",
            default = 500)

    def check_blender_connect(self):
        return 'addon_blender_connect' in  bpy.context.preferences.addons.keys()

    def check_json_nodetree(self):
        return 'addon_jsonnodetree' in  bpy.context.preferences.addons.keys()


    def draw(self, context):

        
        layout = self.layout

        layout.prop(self, "runtimeFile")
        layout.prop(self, "outputPath")
        layout.prop(self, "modelsPath")
        layout.prop(self, "animationsPath")
        layout.prop(self, "materialsPath")
        layout.prop(self, "techniquesPath")
        layout.prop(self, "texturesPath")
        layout.prop(self, "objectsPath")
        layout.prop(self, "scenesPath")
        row = layout.row()
        row.label(text="Max number of bones:")
        row.prop(self, "bonesPerGeometry")
        row.prop(self, "bonesPerVertex")
        row = layout.row()
        row.label(text="Report window:")
        row.prop(self, "reportWidth")
        row.prop(self, "maxMessagesCount")


##############################################
##              USER-DATA-LIST
##############################################
class KeyValue(bpy.types.PropertyGroup):
    key : bpy.props.StringProperty(name="key",default="key")
    value : bpy.props.StringProperty(name="value",default="value")

class UL_URHO_LIST_USERDATA(bpy.types.UIList):
    """KeyValue UIList."""

    def draw_item(self, context, layout, data, item, icon, active_data,active_propname, index):

        # We could write some code to decide which icon to use here...
        if item.key.lower()=="tag":
            custom_icon = 'EVENT_T'
        else:
            custom_icon = 'TEXT'

        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
#            layout.label(item.key, icon = custom_icon)
 #           layout.label(item.value)
            layout.prop(item,"key",  icon=custom_icon,text="")
            layout.prop(item,"value",text="")

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


BUTTON_MAPPING={}


class UL_URHO_LIST_CREATE_GENERIC(bpy.types.Operator):
    """Add a new item to the list."""

    bl_idname = "urho_button.generic"
    bl_label = "Add a new item"

    typeName : bpy.props.StringProperty()
    objectName : bpy.props.StringProperty(default="")

    def execute(self, context):
        global BUTTON_MAPPING
        BUTTON_MAPPING[self.typeName](self,context)
        return{'FINISHED'}



class UL_URHO_LIST_ITEM_USERDATA(bpy.types.Operator):
    """Add a new item to the list."""

    bl_idname = "urho_keyvalue.new_item"
    bl_label = "Add a new item"

    def execute(self, context):
        context.active_object.user_data.add()

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_DEL_USERDATA(bpy.types.Operator):
    """Delete the selected item from the list."""

    bl_idname = "urho_keyvalue.delete_item"
    bl_label = "Deletes an item"

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.user_data

    def execute(self, context):
        kv_list = context.active_object.user_data
        index = context.active_object.list_index_userdata

        kv_list.remove(index)
        context.active_object.list_index_userdata = min(max(0, index - 1), len(kv_list) - 1)

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_MOVE_USERDATA(bpy.types.Operator):
    """Move an item in the list."""

    bl_idname = "urho_keyvalue.move_item"
    bl_label = "Move an item in the list"

    direction : bpy.props.EnumProperty(items=(('UP', 'Up', ""),
                                              ('DOWN', 'Down', ""),))

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.user_data

    def move_index(self):
        """ Move  """

        index = bpy.context.active_object.list_index_userdata
        list_length = len(bpy.context.active_object.user_data) - 1  # (index starts at 0)
        new_index = index + (-1 if self.direction == 'UP' else 1)

        bpy.context.active_object.list_index_userdata = max(0, min(new_index, list_length))

    def execute(self, context):
        kv_list = context.active_object.user_data
        index = context.active_object.list_index_userdata

        neighbor = index + (-1 if self.direction == 'UP' else 1)
        kv_list.move(neighbor, index)
        self.move_index()

        return{'FINISHED'}

##############################################
##              LIST - NODETREES
##############################################
##TODO: Try to unify the list handling (userdata,nodetree) 

def poll_component_nodetree(self,object):
    return object.bl_idname=="urho3dcomponents"

def poll_material_nodetree(self,object):
    return object.bl_idname=="urho3dmaterials"


class NodetreeInfo(bpy.types.PropertyGroup):
    nodetreePointer : bpy.props.PointerProperty(type=bpy.types.NodeTree,poll=poll_component_nodetree)



class UL_URHO_LIST_NODETREE(bpy.types.UIList):
    """KeyValue UIList."""

    def draw_item(self, context, layout, data, item, icon, active_data,active_propname, index):
        custom_icon = 'NODETREE'
        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            c = layout.column()
            row = c.row()
            split = row.split(factor=0.05)
            c = split.column()
            c.label(text="")

            split = split.split()
            c= split.column()
            #layout.label(item.nodetreeName, icon = custom_icon)
            #c.prop_search(item,"nodetreeName",bpy.data,"node_groups",text="")
            c.prop(item,"nodetreePointer")
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


class UL_URHO_LIST_ITEM_NODETREE(bpy.types.Operator):
    """Add a new item to the list."""

    bl_idname = "urho_nodetrees.new_item"
    bl_label = "Add a new item"


    def execute(self, context):
        context.active_object.nodetrees.add()

        return{'FINISHED'}

class UL_URHO_NODETREE_SET_NODETREE_TO_SELECTED(bpy.types.Operator):
    """Set this material-node for all selected objects (slot 0)"""

    bl_idname = "urho_nodetrees.set_selected"
    bl_label = "Apply Material to Selection(Slot0)"

    material_nt_name : bpy.props.StringProperty()

    def execute(self, context):

        print("call with %s" % self.material_nt_name)


        if self.material_nt_name not in bpy.data.node_groups:
            print("couldn't find nodetree:%s" % self.material_nt_name)
            return
        
        material_node_tree = bpy.data.node_groups[self.material_nt_name]

        print("FOUND TREE:%s" % material_node_tree.name)

        for obj in bpy.context.selected_objects:
            if obj.type!="MESH":
                print("NO MESH: %s" % obj.name)
                continue

            print("adding to %s" % obj.name)                
            if len(obj.data.materialNodetrees)==0:
                obj.data.materialNodetrees.add()
                
            ntInfo = obj.data.materialNodetrees[0]
            ntInfo.nodetreePointer = material_node_tree
                
        return{'FINISHED'}



class UL_URHO_LIST_ITEM_DEL_NODETREE(bpy.types.Operator):
    """Delete the selected item from the list."""

    bl_idname = "urho_nodetrees.delete_item"
    bl_label = "Deletes an item"

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type=="MESH" and context.active_object.nodetrees

    def execute(self, context):
        currentlist = context.active_object.nodetrees
        index = context.active_object.list_index_nodetrees

        currentlist.remove(index)
        context.active_object.list_index_nodetrees = min(max(0, index - 1), len(currentlist) - 1)

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_MOVE_NODETREE(bpy.types.Operator):
    """Move an item in the list."""

    bl_idname = "urho_nodetrees.move_item"
    bl_label = "Move an item in the list"

    direction : bpy.props.EnumProperty(items=(('UP', 'Up', ""),
                                              ('DOWN', 'Down', ""),))

    @classmethod
    def poll(cls, context):
        return context.active_object and  context.active_object.type=="MESH" and context.active_object.nodetrees

    def move_index(self):
        """ Move  """

        index = bpy.context.active_object.list_index_nodetrees
        list_length = len(bpy.context.active_object.nodetrees) - 1  # (index starts at 0)
        new_index = index + (-1 if self.direction == 'UP' else 1)

        bpy.context.active_object.list_index_nodetrees = max(0, min(new_index, list_length))

    def execute(self, context):
        currentlist = context.active_object.nodetrees
        index = context.active_object.list_index_nodetrees

        neighbor = index + (-1 if self.direction == 'UP' else 1)
        currentlist.move(neighbor, index)
        self.move_index()

        return{'FINISHED'}

##############################################
##              LIST - MATERIAL NODETREES
##############################################
##TODO: Try to unify the list handling (userdata,nodetree) 

class MaterialNodetreeInfo(bpy.types.PropertyGroup):
    nodetreePointer : bpy.props.PointerProperty(type=bpy.types.NodeTree,poll=poll_material_nodetree)

## TODO: this is actually unnecessary (same as for logic nodetrees)
class UL_URHO_LIST_MATERIAL_NODETREE(bpy.types.UIList):
    """KeyValue UIList."""

    def draw_item(self, context, layout, data, item, icon, active_data,active_propname, index):
        custom_icon = 'NODETREE'
        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            c = layout.column()
            row = c.row()
            split = row.split(factor=0.05)
            c = split.column()
            c.label(text="")

            split = split.split()
            c= split.column()
            #layout.label(item.nodetreeName, icon = custom_icon)
            #c.prop_search(item,"nodetreeName",bpy.data,"node_groups",text="")
            c.prop(item,"nodetreePointer")
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


class UL_URHO_LIST_ITEM_MATERIAL_NODETREE(bpy.types.Operator):
    """Add a new item to the list."""

    bl_idname = "urho_material_nodetrees.new_item"
    bl_label = "Add a new item"


    def execute(self, context):
        context.active_object.data.materialNodetrees.add()

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_DEL_MATERIAL_NODETREE(bpy.types.Operator):
    """Delete the selected item from the list."""

    bl_idname = "urho_material_nodetrees.delete_item"
    bl_label = "Deletes an item"

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type=="MESH"

    def execute(self, context):
        currentlist = context.active_object.data.materialNodetrees
        index = context.active_object.data.list_index_nodetrees

        currentlist.remove(index)
        
        context.active_object.data.list_index_nodetrees = min(max(0, index - 1), len(currentlist) - 1)
        bpy.context.active_object.active_material_index = context.active_object.data.list_index_nodetrees
        return{'FINISHED'}


class UL_URHO_LIST_ITEM_MOVE_MATERIAL_NODETREE(bpy.types.Operator):
    """Move an item in the list."""

    bl_idname = "urho_material_nodetrees.move_item"
    bl_label = "Move an item in the list"

    direction : bpy.props.EnumProperty(items=(('UP', 'Up', ""),
                                              ('DOWN', 'Down', ""),))

    @classmethod
    def poll(cls, context):
        return context.active_object and  context.active_object.type=="MESH" and context.active_object.data.materialNodetrees

    def move_index(self):
        """ Move  """

        index = bpy.context.active_object.data.list_index_nodetrees
        list_length = len(bpy.context.active_object.data.materialNodetrees) - 1  # (index starts at 0)
        new_index = index + (-1 if self.direction == 'UP' else 1)

        bpy.context.active_object.data.list_index_nodetrees = max(0, min(new_index, list_length))
        bpy.context.active_object.active_material_index = bpy.context.active_object.data.list_index_nodetrees        

    def execute(self, context):
        currentlist = context.active_object.data.materialNodetrees
        index = context.active_object.data.list_index_nodetrees

        neighbor = index + (-1 if self.direction == 'UP' else 1)
        currentlist.move(neighbor, index)
        self.move_index()

        return{'FINISHED'}



##############################################
##              LIST - LODS
##############################################
##TODO: Try to unify the list handling (userdata,nodetree,lods) 

def nextLodSetIDX():
    new_idx = bpy.data.worlds[0].lodset_counter + 1
    bpy.data.worlds[0].lodset_counter = new_idx
    return new_idx
    
# button-logic used within the generic-button
def OpCreateLodSet(self,context):
    lodset = bpy.data.worlds[0].lodsets.add()
    lodset.lodset_id = nextLodSetIDX()
    lodset.name="new-lodset "+str(lodset.lodset_id)
    bpy.context.active_object.lodsetID=lodset.lodset_id

BUTTON_MAPPING["create_lodset"]=OpCreateLodSet

# button-logic used within the generic-button
def OpDeleteLodSet(self,context):
    idx = getLodSetWithID(bpy.context.active_object.lodsetID,True)
    lodset = bpy.data.worlds[0].lodsets.remove(idx)

BUTTON_MAPPING["delete_lodset"]=OpDeleteLodSet


## make sure to keep the lodsetID to set selected object


def getLodSetName(self):
    # print("get")
    if self.lodsetID == -1:
        return ""

    lodset = getLodSetWithID(self.lodsetID)

    if lodset:
        return lodset.name
    else:
        return ""

def setLodSetName(self,value):
    if value == "":
        #print("RESETID")
        self.lodsetID = -1
    else:
        #print("set %s=%s" % (self.name, str(value) ))
        for lodset in bpy.data.worlds[0].lodsets:
            if lodset.name == value:
                self.lodsetID = lodset.lodset_id
                return

        self.lodsetID = -1
        #print("assigned ID %s" % getID(nodetree))            
            
def updateLodSetName(self,ctx):
    pass
## make sure the actual name of the lodset is unique
def lodsetNameExists(name):
    for lodset in bpy.data.worlds[0].lodsets:
        if lodset.name == name:
            return True
    return False

def getLodSetDataName(self):
    return self.name

def setLodSetDataName(self,value):
    while lodsetNameExists(value):
        value = value + "_"
    self.lodset_name = value

## -- DATA OBJECTS --
class LODData(bpy.types.PropertyGroup):
    #meshName = bpy.props.StringProperty(get=getMeshName,set=setMeshName,update=updateMeshName)
    #meshID = bpy.props.IntProperty()
    meshObj : bpy.props.PointerProperty(type=bpy.types.Mesh)
    distance : bpy.props.IntProperty(name="distance")
    decimate : bpy.props.FloatProperty(name="decimateFactor",default=1.0,precision=3,max=1.0,min=0.0)


def armature_object_poll(self,object):
    return object.type=="ARMATURE"

class LODSet(bpy.types.PropertyGroup):
    lodset_id : bpy.props.IntProperty()
    name : bpy.props.StringProperty(default="lodset")
    lodset_name : bpy.props.StringProperty(default="lodset",get=getLodSetDataName,set=setLodSetDataName)
    lods : bpy.props.CollectionProperty(type=LODData)
    lods_idx : bpy.props.IntProperty()
    armatureObj :  bpy.props.PointerProperty(type=bpy.types.Object,poll=armature_object_poll)
        

## -- VISUALS --
class UL_LODSet(bpy.types.UIList):
    """LODSet List"""

    def draw_item(self, context, layout, data, item, icon, active_data,active_propname, index):
        
        custom_icon = 'MESH'
        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(item,"lodset_Name")
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(item,"lodset_Name")


class UL_URHO_LIST_LOD(bpy.types.UIList):
    """LOD UIList."""

    def draw_item(self, context, layout, data, item, icon, active_data,active_propname, index):

        # We could write some code to decide which icon to use here...
        #if item.key.lower()=="tag":
        #    custom_icon = 'INLINK'
        #else:
        #    custom_icon = 'TEXT'
        
        custom_icon = 'MESH'
        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            #layout.prop_search(item,"meshName",bpy.data,"meshes","Mesh")
            c = layout.column()
            row = c.row()
            split = row.split(factor=0.5)
            c = split.column()
            c.prop(item,"meshObj")

            split = split.split()
            c= split.column()
            #layout.label(item.nodetreeName, icon = custom_icon)
            c.prop(item,"distance")
            c = split.column()
            if (data.armatureObj):
                c.enabled=False
            c.prop(item,"decimate")


          #  layout.prop(item,"meshObj")
          #  layout.prop(item,"distance")
            ## todo: make this smaller
           # layout.prop(item,"decimate",text="")
            if item.meshObj:
                layout.operator("urho.selectmesh",icon="RESTRICT_SELECT_OFF",text="").meshname=item.meshObj.name

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


class UL_URHO_LIST_ITEM_LOD(bpy.types.Operator):
    """Add a new item to the list."""

    bl_idname = "urho_lod.new_item"
    bl_label = "Add a new item"

    def execute(self, context):
        lodset = getLodSetWithID(context.active_object.lodsetID)
        
        if lodset:
            lodset.lods.add()
        else:
            pass

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_DEL_LOD(bpy.types.Operator):
    """Delete the selected item from the list."""

    bl_idname = "urho_lod.delete_item"
    bl_label = "Deletes an item"

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.lodsetID

    def execute(self, context):
        lodset = getLodSetWithID(context.active_object.lodsetID)
        currentlist = lodset.lods
        index = lodset.lods_idx

        currentlist.remove(index)
        lodset.lods_idx = min(max(0, index - 1), len(currentlist) - 1)

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_MOVE_LOD(bpy.types.Operator):
    """Move an item in the list."""

    bl_idname = "urho_lod.move_item"
    bl_label = "Move an item in the list"

    direction : bpy.props.EnumProperty(items=(('UP', 'Up', ""),
                                              ('DOWN', 'Down', ""),))

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.lodsetID

    def move_index(self):
        """ Move  """

        lodset = getLodSetWithID(bpy.context.active_object.lodsetID)
        index = lodset.lods_idx
        currentlist = lodset.lods
        list_length = len(currentlist) - 1  # (index starts at 0)
        new_index = index + (-1 if self.direction == 'UP' else 1)

        lodset.lods_idx = max(0, min(new_index, list_length))

    def execute(self, context):
        lodset = getLodSetWithID(bpy.context.active_object.lodsetID)
        currentlist = lodset.lods
        index = lodset.lods_idx

        neighbor = index + (-1 if self.direction == 'UP' else 1)
        currentlist.move(neighbor, index)
        self.move_index()

        return{'FINISHED'}


##################################################
##
##################################################


class UrhoExportMeshSettings(bpy.types.PropertyGroup):
    def get_uvs(self,context):
        uvs_result=[('-1',"none","none",-1)]
        idx = 0
        for uv in self.id_data.uv_layers:
            uvs_result.append((str(idx),uv.name,uv.name,idx))
            idx = idx + 1
        return uvs_result

    def get_uv1(self):
        if self.active_uv_as_uv1:
            return self.id_data.uv_layers.active_index
        return self.uv1_idx

    def get_export_uv1(self):
        if self.active_uv_as_uv1:
            return int(self.auto_uv1_idx)
        else:
            return int(self.manual_uv1_idx)

    def get_export_uv2(self):
        if self.use_uv2:
            return int(self.manual_uv2_idx)
        else:
            return -1

    def copyInto(self, obj_vertex):
        obj_vertex.export_pos = self.export_pos
        obj_vertex.export_norm = self.export_norm
        obj_vertex.export_tan = self.export_tan
        obj_vertex.export_uv = self.export_uv
        obj_vertex.export_vcol = self.export_vcol
        obj_vertex.export_morph = self.export_morph
        obj_vertex.export_weight = self.export_weight
        obj_vertex.active_uv_as_uv1 = self.active_uv_as_uv1
        #obj_vertex.auto_uv1_idx = self.auto_uv1_idx
        obj_vertex.manual_uv1_idx = self.manual_uv1_idx
        obj_vertex.use_uv2 = self.use_uv2
        obj_vertex.manual_uv2_idx = self.manual_uv2_idx        

    def update(self,context):
        if self.export_tan:
            if not self.export_pos or not self.export_norm or not self.export_uv:
                self.export_tan=False

    export_pos : bpy.props.BoolProperty(default=True,update=update)
    export_norm: bpy.props.BoolProperty(default=True,update=update)
    export_tan: bpy.props.BoolProperty(default=False,update=update)
    export_uv : bpy.props.BoolProperty(default=True,update=update)
    export_vcol : bpy.props.BoolProperty(default=False,update=update)
    export_morph: bpy.props.BoolProperty(default=False,update=update)
    export_weight: bpy.props.BoolProperty(default=False,update=update)
    #export_weight: bpy.props.BoolProperty(default=False,update=update)

    active_uv_as_uv1 : bpy.props.BoolProperty(default=True) # export the active uv as uv1
    auto_uv1_idx : bpy.props.EnumProperty(items=get_uvs,get=get_uv1) 
    manual_uv1_idx : bpy.props.EnumProperty(items=get_uvs)
    use_uv2 : bpy.props.BoolProperty(default=False) 
    manual_uv2_idx : bpy.props.EnumProperty(items=get_uvs) 

def PrefixFile(input):
    global_settings = bpy.data.worlds[0].global_settings
    scenename = bpy.context.scene.name

    return "%s-%s-%s" % (global_settings.file_id,scenename,input)



class UrhoExportGlobalSettings(bpy.types.PropertyGroup):
    file_id : bpy.props.IntProperty(default=-1) # a unique id that will optionally prefixed to your model-filename 
    

def renderpath_items(self,context):
    try: 
        return JSONNodetree.globalData["renderPaths_elemitems"]
    except:
        #print("Could not retrieve renderPaths")
        return [("RenderPaths/Forward.xml","RenderPaths/Forward.xml","RenderPaths/Forward.xml",9902871)]

def zone_cubetexture_items(self,context):
    try: 
        return zone_cubemap
    except:
        #print("Could not retrieve renderPaths")
        return [("None","None","None",0)]        

# Here we define all the UI objects to be added in the export panel
class UrhoExportSettings(bpy.types.PropertyGroup):

    # This is called each time a property (created with the parameter 'update')
    # changes its value
    def update_func(self, context):
        # Avoid infinite recursion
        if self.updatingProperties:
            return
        self.updatingProperties = True

        # Save preferred output path
        addonPrefs = context.preferences.addons[__name__].preferences
        
        print("UPDATE")
        
        if self.outputPath:
            # REMOVE THIS?
            print("OUTPUT")
            #addonPrefs.outputPath = self.outputPath

            bpy.data.worlds[0].jsonNodes.path = "%s__blender_material.json" % bpy.path.abspath(self.outputPath)
            print("--")


        # Skeleton implies weights    
        if self.skeletons:
            self.geometryWei = True
            self.objAnimations = False
        else:
            self.geometryWei = False
            self.animations = False
        # Use Fcurves only for actions
        if not ('ACTION' in self.animationSource):
            self.actionsByFcurves = False
        # Morphs need geometries    
        if not self.geometries:
            self.morphs = False
        # Tangent needs position, normal and UV
        if not self.geometryPos or not self.geometryNor or not self.geometryUV:
            self.geometryTan = False
        # Morph normal needs geometry normal
        if not self.geometryNor:
            self.morphNor = False
        # Morph tangent needs geometry tangent
        if not self.geometryTan:
            self.morphTan = False
        # Morph tangent needs normal
        if not self.morphNor:
            self.morphTan = False
        # Select errors and merge are incompatible
        if self.selectErrors:
            self.merge = False
            
        self.updatingProperties = False

    def update_func2(self, context):
        if self.updatingProperties:
            return
        self.updatingProperties = True
        # Select errors and merge are incompatible
        if self.merge:
            self.selectErrors = False

        self.updatingProperties = False


    def ExportNoGeo(self,context):
        #ExecuteAddon(context, True, True )
        settings = context.scene.urho_exportsettings
        if settings.runtimeAutoUpdateTransforms:
            bpy.ops.urho.exportcommand()
        #bpy.ops.urho.export(ignore_geo_skel_anim=True)


    def update_subfolders(self, context):
        # Move folders between the output path and the subfolders
        # (this should have been done with operators)
        if self.updatingProperties:
            return
        self.updatingProperties = True
        if self.addDir:
            # Move the last folder from the output path to the subfolders
            self.addDir = False
            last = os.path.basename(os.path.normpath(self.outputPath))
            ilast = self.outputPath.rindex(last)
            if last and ilast >= 0:
                self.outputPath = self.outputPath[:ilast]
                self.modelsPath = os.path.join(last, self.modelsPath)
                self.animationsPath = os.path.join(last, self.animationsPath)
                self.materialsPath = os.path.join(last, self.materialsPath)
                self.techniquesPath = os.path.join(last, self.techniquesPath)
                self.texturesPath = os.path.join(last, self.texturesPath)
                self.objectsPath = os.path.join(last, self.objectsPath)
                self.scenesPath = os.path.join(last, self.scenesPath)
        if self.removeDir:
            # Move the first common folder from the subfolders to the output path
            self.removeDir = False
            ifirst = self.modelsPath.find(os.path.sep) + 1
            first = self.modelsPath[:ifirst]
            if first and \
               self.animationsPath.startswith(first) and \
               self.materialsPath.startswith(first) and \
               self.techniquesPath.startswith(first) and \
               self.texturesPath.startswith(first) and \
               self.objectsPath.startswith(first) and \
               self.scenesPath.startswith(first):
                self.outputPath = os.path.join(self.outputPath, first)
                self.modelsPath = self.modelsPath[ifirst:]
                self.animationsPath = self.animationsPath[ifirst:]
                self.materialsPath = self.materialsPath[ifirst:]
                self.techniquesPath = self.techniquesPath[ifirst:]
                self.texturesPath = self.texturesPath[ifirst:]
                self.objectsPath = self.objectsPath[ifirst:]
                self.scenesPath = self.scenesPath[ifirst:]
        if self.addSceneDir:
            # Append the scene name to the subfolders
            self.addSceneDir = False
            sceneName = context.scene.name
            last = os.path.basename(os.path.normpath(self.modelsPath))
            if sceneName != last:
                self.modelsPath = os.path.join(self.modelsPath, sceneName)
                self.animationsPath = os.path.join(self.animationsPath, sceneName)
                self.materialsPath = os.path.join(self.materialsPath, sceneName)
                self.techniquesPath = os.path.join(self.techniquesPath, sceneName)
                self.texturesPath = os.path.join(self.texturesPath, sceneName)
                self.objectsPath = os.path.join(self.objectsPath, sceneName)
                self.scenesPath = os.path.join(self.scenesPath, sceneName)
        self.updatingProperties = False

    def errors_update_func(self, context):
        if self.updatingProperties:
            return
        self.updatingProperties = True
        errorName = self.errorsEnum
        self.errorsEnum = 'NONE'
        self.updatingProperties = False
        selectErrors(context, self.errorsMem, errorName)
        
    def errors_items_func(self, context):
        items = [('NONE', "", ""),
                 ('ALL',  "all", "")]
        for error in self.errorsMem.Names():
            items.append( (error, error, "") )
        return items

    # Revert all the export settings back to their default values
    def reset(self, context): 
        
        addonPrefs = context.preferences.addons[__name__].preferences

        self.updatingProperties = False

        self.minimize = False
        self.onlyErrors = False
        self.showDirs = False

        self.useSubDirs = True
        self.fileOverwrite = False

        self.source = 'ALL'
        self.scale = 1.0
        self.modifiers = False
        self.modifiersRes = 'PREVIEW'
        self.origin = 'LOCAL'
        self.selectErrors = True
        self.forceElements = False
        self.merge = False
        self.mergeNotMaterials = False
        self.geometrySplit = False
        self.lods = False
        self.strictLods = True
        self.optimizeIndices = False

        self.skeletons = False
        self.onlyKeyedBones = False
        self.onlyDeformBones = False
        self.onlyVisibleBones = False
        self.actionsByFcurves = False
        self.parentBoneSkinning = False
        self.derigify = False
        self.clampBoundingBox = False

        self.animations = False
        self.objAnimations = False
        self.animationSource = 'USED_ACTIONS'        
        self.onlyDeformBones = False
        self.animationExtraFrame = True
        self.animationTriggers = False
        self.animationRatioTriggers = False
        self.animationPos = True
        self.animationRot = True
        self.animationSca = False
        self.filterSingleKeyFrames = False

        self.geometries = True
        self.geometryPos = True
        self.geometryNor = True
        self.geometryCol = False
        self.geometryColAlpha = False
        self.geometryUV = False
        self.geometryUV2 = False
        self.geometryTan = False
        self.geometryWei = False

        self.morphs = False
        self.morphNor = True
        self.morphTan = False

        self.materials = False
        self.materialsList = False
        self.textures = False

        self.prefabs = True
        self.individualPrefab = False
        self.collectivePrefab = False
        self.scenePrefab = False
        self.sceneCreateZone = False
        self.sceneCreateSkybox = False
        self.trasfObjects = False
        self.physics = 'INDIVIDUAL'
        self.shape = 'TRIANGLEMESH'

    # Revert the output paths back to their default values
    def reset_paths(self, context, forced):

        addonPrefs = context.preferences.addons[__name__].preferences

        if forced or (not self.outputPath and addonPrefs.outputPath):
            self.outputPath = addonPrefs.outputPath

        if forced or (not self.modelsPath and addonPrefs.modelsPath):
            self.modelsPath = addonPrefs.modelsPath
            self.animationsPath = addonPrefs.animationsPath
            self.materialsPath = addonPrefs.materialsPath
            self.techniquesPath = addonPrefs.techniquesPath
            self.texturesPath = addonPrefs.texturesPath
            self.objectsPath = addonPrefs.objectsPath
            self.scenesPath = addonPrefs.scenesPath

    # --- Accessory ---

    updatingProperties : BoolProperty(default = False)

    minimize : BoolProperty(
            name = "Minimize",
            description = "Minimize the export panel",
            default = False)

    onlyErrors : BoolProperty(
            name = "Log errors",
            description = "Show only warnings and errors in the log",
            default = False)

    showLog : BoolProperty(
            name = "Show Log after export",
            description = "Show log after export",
            default = True)            

    showDirs : BoolProperty(
            name = "Show dirs",
            description = "Show the dirs list",
            default = False)

    addDir : BoolProperty(
            name = "Output folder to subfolders",
            description = "Move the last output folder to the subfolders",
            default = False,
            update = update_subfolders)

    removeDir : BoolProperty(
            name = "Subfolders to output folder",
            description = "Move a common subfolder to the output folder",
            default = False,
            update = update_subfolders)

    addSceneDir : BoolProperty(
            name = "Scene to subfolders",
            description = "Append the scene name to the subfolders",
            default = False,
            update = update_subfolders)

    # --- RUNTIME SETTINGS ---
    runtimeAutoUpdateTransforms : BoolProperty(
            name = "Auto Export on Transform",
            description = "Auto Export on Transform",
            default = True,
            update=PublishRuntimeSettings) 

    runtimeUnstable : BoolProperty(
            name = "Unstable Features",
            description = "activate (even more) unstable features",
            default = False
            )             

    runtimeShowPhysics : BoolProperty(
            name = "Show Physics",
            description = "Show Urho3D-Physics",
            default = False,
            update=PublishRuntimeSettings)  

    runtimeActivatePhysics : BoolProperty(
            name = "Activate Physics",
            description = "Activate Urho3D-Physics",
            default = False,
            update=PublishRuntimeSettings)  


    runtimeShowPhysicsDepth : BoolProperty(
            name = "Show Physics Depth",
            description = "Use depth-test on drawing physics",
            default = False,
            update=PublishRuntimeSettings)    

    runtimeShowSRGB : BoolProperty(
            name = "sRGB",
            description = "enable sRGB",
            default = False,
            update=PublishRuntimeSettings)     

    runtimeUseGamma : BoolProperty(
            name = "gamma",
            description = "enable gamma-correction",
            default = False,
            update=ExportNoGeo)     
    runtimeUseHDR : BoolProperty(
            name = "HDR",
            description = "enable HDR",
            default = False,
            update=ExportNoGeo)     
    runtimeUseBloom : BoolProperty(
            name = "bloom",
            description = "enable bloom",
            default = False,
            update=ExportNoGeo) 
    
    runtimeUseFXAA2 : BoolProperty(
            name = "FXAA2",
            description = "enable FXAA2",
            default = False,
            update=ExportNoGeo)                  

    runtimeRenderPath : EnumProperty(
            name = "RenderPath",
            items = renderpath_items,
            update=ExportNoGeo,
            default=9902871)                       
                  
    runtimeExportComponents : BoolProperty(
            name = "Export Components",
            description = "Export components to be used in Component-Tree",
            default = True,
            update=PublishRuntimeSettings)   

    runtimeExportComponentsMode : EnumProperty(
            name = "Component Export",
            description = "Export components",
            items=(('LITE', "Lite", "Just a selection of components",1),
                   ('ALL', "All", "All registered components",2)),
            default=1,
            update=PublishRuntimeSettings)                  

    runtimeWorkingDir : bpy.props.StringProperty(
                    name="Runtime WorkingDir",
                    description="WorkingDir",
                    maxlen = 512,
                    default = "",
                    subtype='FILE_PATH')

    runtimeFlags : bpy.props.StringProperty(
                    name="runtime flags",
                    description="Runtime Flags that get passed to the 'runtimeflags' argument and can be processed in your runtime",
                    maxlen = 512,
                    default = "")

    # runtimeExportComponents : bpy.props.StringProperty(
    #                 name="component export file",
    #                 description="Override component export-file (default: ./urho3d_components.json)",
    #                 maxlen = 512,
    #                 subtype = "FILE_PATH")   

    enableRuntime2 : bpy.props.BoolProperty(default=False,description="enable a second runtime to be started from within blender")

    runtime2File :  bpy.props.StringProperty(
                    name="Runtime WorkingDir",
                    description="WorkingDir",
                    maxlen = 512,
                    default = "",
                    subtype='FILE_PATH')            


    # --- Output settings ---
    generateSceneHeader : BoolProperty(description="Export cpp-header to access scene-object name/id in code")

    sceneHeaderOutputPath : StringProperty(
            name = "",
            description = "Path where to generate the sceneHeader-file",
            default = "", 
            maxlen = 1024,
            subtype = "DIR_PATH",
            update = update_func)   

    outputPath : StringProperty(
            name = "",
            description = "Path where to export",
            default = "", 
            maxlen = 1024,
            subtype = "DIR_PATH",
            update = update_func)   

    packPath : StringProperty(
            name = "",
            description = "Path where to store your package",
            default = "", 
            maxlen = 1024,
            subtype = "FILE_PATH",
            update = update_func)               

    useSubDirs : BoolProperty(
            name = "Use sub folders",
            description = "Use sub folders inside the output folder (Materials, Models, Textures ...)",
            default = True)

    modelsPath : StringProperty(
            name = "Models",
            description = "Models subpath (relative to output)",
            default="Models")
    animationsPath : StringProperty(
            name = "Animations",
            description = "Animations subpath (relative to output)",
            default="Models")
    materialsPath : StringProperty(
            name = "Materials",
            description = "Materials subpath (relative to output)",
            default="Materials")
    techniquesPath : StringProperty(
            name = "Techniques",
            description = "Techniques subpath (relative to output)",
            default="Techniques")
    texturesPath : StringProperty(
            name = "Textures",
            description = "Textures subpath (relative to output)",
            default="Textures")
    objectsPath : StringProperty(
            name = "Objects",
            description = "Objects subpath (relative to output)",
            default="Objects")
    scenesPath : StringProperty(
            name = "Scenes",
            description = "Scenes subpath (relative to output)",
            default="Scenes")

    fileOverwrite : BoolProperty(
            name = "Files overwrite",
            description = "If enabled existing files are overwritten without warnings",
            default = True)

    # --- Source settings ---
            
    source : EnumProperty(
            name = "Source",
            description = "Objects to be exported",
            items=(('ALL', "All", "all the objects in the scene"),
                   ('ONLY_SELECTED', "Only selected", "only the selected objects in visible layers")),
            default='ALL')



    orientation : EnumProperty(
            name = "Front view",
            description = "Front view of the model",
            items = (('X_MINUS', "Left (--X +Z)", ""),
                     ('X_PLUS',  "Right (+X +Z)", ""),
                     ('Y_MINUS', "Front (--Y +Z)", ""),
                     ('Y_PLUS',  "Back (+Y +Z) *", ""),
                     ('Z_MINUS', "Bottom (--Z --Y)", ""),
                     ('Z_PLUS',  "Top (+Z +Y)", "")),
            default = 'X_PLUS')

    scale : FloatProperty(
            name = "Scale", 
            description = "Scale to apply on the exported objects", 
            default = 1.0,
            min = 0.0, 
            max = 1000.0,
            step = 10,
            precision = 1)

    modifiers : BoolProperty(
            name = "Apply modifiers",
            description = "Apply the object modifiers before exporting",
            default = True)

    modifiersRes : EnumProperty(
            name = "Modifiers setting",
            description = "Resolution setting to use while applying modifiers",
            items = (('PREVIEW', "Preview", "use the Preview resolution setting"),
                     ('RENDER', "Render", "use the Render resolution setting")),
            default = 'RENDER')

    origin : EnumProperty(
            name = "Mesh origin",
            description = "Origin for the position of vertices/bones",
            items=(('GLOBAL', "Global", "Blender's global origin"),
                   ('LOCAL', "Local", "object's local origin (orange dot)")),
            default = 'LOCAL')

    selectErrors : BoolProperty(
            name = "Select vertices with errors",
            description = "If a vertex has errors (e.g. invalid UV, missing UV or color or weights) select it",
            default = True,
            update = update_func)

    errorsMem = ErrorsMem()
    errorsEnum : EnumProperty(
            name = "",
            description = "List of errors",
            items = errors_items_func,
            update = errors_update_func)

    forceElements : BoolProperty(
            name = "Force missing elements",
            description = "If a vertex element (UV, color, weights) is missing add it with a zero value",
            default = False)

    ignoreHidden : BoolProperty(
            name = "Don't export hidden objects",
            description = "Don't export hidden objects",
            default = False)  

    wiredAsEmpty : BoolProperty(
            name = "Export wired MeshesNodes as empties",
            description = "MeshesNodes that are set to wired in ObjectPanel are exported as empties",
            default = False)                

    exportOnSave : BoolProperty(
            name = "Export Data on Save",
            description = "Export Data after Saving the blend",
            default = False) 
    
    export_on_save_modes = [ 
        ( "ALL","All Scene","All scene",1 ),
        ( "NOGEO","No Geometry","No Geometry",2 ),
        ( "MAT","Only Material","Only Materials",3 )
    ]

    exportOnSaveMode : EnumProperty(items=export_on_save_modes,default=1,description="Specific what export mode to use on save!")

    exportGroupsAsObject : BoolProperty(
            name = "Export Instanced Collections as PrefabObject",
            description = "Export Collections as PrefabObject and write meta data into the group-instance-empties",
            default = True)   

    exportObjectCollectionAsTag   : BoolProperty(
            name = "add collections as tag",
            description = "Export object's collection containment as tag",
            default = True)                                                  

    merge : BoolProperty(
            name = "Merge objects",
            description = ("Merge all the objects in a single file, one common geometry for each material. "
                           "It uses the current object name."),
            default = False,
            update = update_func2)

    mergeNotMaterials : BoolProperty(
            name = "Don't merge materials",
            description = "Create a different geometry for each material of each object",
            default = False)

    geometrySplit : BoolProperty(
            name = "One vertex buffer per object",
            description = "Split each object into its own vertex buffer",
            default = False)

    lods : BoolProperty(
            name = "Use LODs",
            description = "Search for the LOD distance if the object name, objects with the same name are added as LODs",
            default = True)

    strictLods : BoolProperty(
            name = "Strict LODs",
            description = "Add a new vertex if the LOD0 does not contain a vertex with the exact same position, normal and UV",
            default = True)
            
    optimizeIndices : BoolProperty(
            name = "Optimize indices (slow)",
            description = "Linear-Speed vertex cache optimisation",
            default = False)

    # --- Components settings ---

    skeletons : BoolProperty(
            name = "Skeletons",
            description = "Export model armature bones",
            default = False,
            update = update_func)

    onlyKeyedBones : BoolProperty(
            name = "Only keyed bones",
            description = "In animinations export only bones with keys",
            default = False)

    onlyDeformBones : BoolProperty(
            name = "Only deform bones",
            description = "Don't export bones without Deform and its children",
            default = False,
            update = update_func2)
            
    onlyVisibleBones : BoolProperty(
            name = "Only visible bones",
            description = "Don't export bones not visible and its children",
            default = False,
            update = update_func2)

    actionsByFcurves : BoolProperty(
            name = "Read actions by Fcurves",
            description = "Should be much faster than updating the whole scene, usable only for Actions and for Quaternion rotations",
            default = False)

    derigify : BoolProperty(
            name = "Derigify",
            description = "Remove extra bones from Rigify armature",
            default = False,
            update = update_func)

    clampBoundingBox : BoolProperty(
            name = "Clamp bones bounding box",
            description = "Clamp each bone bounding box between bone head & tail. Use case: ragdoll, IK...",
            default = False)

    parentBoneSkinning : BoolProperty(
            name = "Use skinning for parent bones",
            description = "If an object has a parent of type BONE use a 100% skinning on its vertices "
                          "(use this only for a quick prototype)",
            default = False,
            update = update_func)

    animations : BoolProperty(
            name = "Animations",
            description = "Export bones animations (Skeletons needed)",
            default = False)

    objAnimations : BoolProperty(
            name = "of objects",
            description = "Export objects animations (without Skeletons)",
            default = False)

    animationSource : EnumProperty(
            name = "",
            items = (('ALL_ACTIONS', "All Actions", "Export all the actions in memory"),
                    ('CURRENT_ACTION', "Current Action", "Export the object's current action linked in the Dope Sheet editor"),
                    ('USED_ACTIONS', "Actions used in tracks", "Export only the actions used in NLA tracks"),
                    ('SELECTED_ACTIONS', "Selected Strips' Actions", "Export the actions of the current selected NLA strips"),
                    ('SELECTED_STRIPS', "Selected Strips", "Export the current selected NLA strips"),
                    ('SELECTED_TRACKS', "Selected Tracks", "Export the current selected NLA tracks"),
                    ('ALL_STRIPS', "All Strips", "Export all NLA strips"),
                    ('ALL_TRACKS', "All Tracks (not muted)", "Export all NLA tracks"),
                    ('TIMELINE', "Timelime", "Export the timeline (NLA tracks sum)")),
            default = 'USED_ACTIONS',
            update = update_func)

    animationExtraFrame : BoolProperty(
            name = "Ending extra frame",
            description = "In Blender to avoid pauses in a looping animation you normally want to skip the last frame "
                          "when it is the same as the first one. Urho needs this last frame, use this option to add it. "
                          "It is needed only when using the Timeline or Nla-Tracks.",
            default = True)

    animationTriggers : BoolProperty(
            name = "Export markers as triggers",
            description = "Export action pose markers (for actions, strips and tracks) or scene markers (for timeline) "
                          "as triggers, the time is expressed in seconds",
            default = False)

    animationRatioTriggers : BoolProperty(
            name = "Normalize time",
            description = "Export the time of triggers as a number from 0 (start) to 1 (end)",
            default = False)

    #---------------------------------

    animationPos : BoolProperty(
            name = "Position",
            description = "Within animations export bone positions",
            default = True)

    animationRot : BoolProperty(
            name = "Rotation",
            description = "Within animations export bone rotations",
            default = True)

    animationSca : BoolProperty(
            name = "Scale",
            description = "Within animations export bone scales",
            default = False)

    filterSingleKeyFrames : BoolProperty(
            name = "Remove single tracks",
            description = "Do not export tracks which contain only one keyframe, useful for layered animations",
            default = False)

    geometries : BoolProperty(
            name = "Geometries",
            description = "Export vertex buffers, index buffers, geometries, lods",
            default = True,
            update = update_func)

    geometryPos : BoolProperty(
            name = "Position",
            description = "Within geometry export vertex position",
            default = True,
            update = update_func)

    geometryNor : BoolProperty(
            name = "Normal",
            description = "Within geometry export vertex normal (enable 'Auto Smooth' to export custom normals)",
            default = True,
            update = update_func)

    geometryCol : BoolProperty(
            name = "Color",
            description = "Within geometry export vertex color",
            default = False)

    geometryColAlpha : BoolProperty(
            name = "Alpha",
            description = "Within geometry export vertex alpha (append _ALPHA to the color layer name)",
            default = False)

    geometryUV : BoolProperty(
            name = "UV",
            description = "Within geometry export vertex UV",
            default = False,
            update = update_func)

    geometryUV2 : BoolProperty(
            name = "UV2",
            description = "Within geometry export vertex UV2 (append _UV2 to the texture name)",
            default = False,
            update = update_func)

    geometryTan : BoolProperty(
            name = "Tangent",
            description = "Within geometry export vertex tangent (Position, Normal, UV needed)",
            default = False,
            update = update_func)

    geometryWei : BoolProperty(
            name = "Weights",
            description = "Within geometry export vertex bones weights (Skeletons needed)",
            default = False)

    morphs : BoolProperty(
            name = "Morphs (shape keys)",
            description = "Export vertex morphs (Geometries needed)",
            default = False)

    morphNor : BoolProperty(
            name = "Normal",
            description = "Within morph export vertex normal (Geometry Normal needed)",
            default = True,
            update = update_func)

    morphTan : BoolProperty(
            name = "Tangent",
            description = "Within morph export vertex tangent (Morph Normal, Geometry Tangent needed)",
            default = False,
            update = update_func)

    materials : BoolProperty(
            name = "Export materials",
            description = "Export XML materials",
            default = False,
            update = update_func)

    create_default_material_nodetree : BoolProperty(
        name="Create Default Material-Nodetree",
        default=True,
        description="Create Default Material-Nodetree"
    )

    create_nodetree_from_material: StringProperty(
        name="Create Urho3D-Material from Blender-Material",
        default="",
        description="Try to create urho3d-material from blender materials"
    )

    materialsList : BoolProperty(
            name = "Materials text list",
            description = "Write a txt file with the list of materials filenames",
            default = False)

    textures : BoolProperty(
            name = "Copy textures",
            description = "Copy diffuse textures",
            default = False,
            update = update_func)            

    prefabs : BoolProperty(
            name = "Export Urho Prefabs",
            description = "Export Urho3D XML objects (prefabs)",
            default = True,
            update = update_func)

    individualPrefab : BoolProperty(
            name = "Individual Prefabs",
            description = "Create one prefab per exported object (so if \"Merge objects\" option is checked, export one prefab for the merged object only)",
            default = False,
            update = update_func)

    individualPrefab_onlyRootObject : BoolProperty(
            name = "Only Root-Objects",
            description = "Only export individual ROOT objects and pack children recursively inside",
            default = True)


    collectivePrefab : BoolProperty(
            name = "One Collective",
            description = "Create one unic/global prefab containing every exported objects. An empty root node holds the objects.",
            default = False,
            update = update_func)

    scenePrefab : BoolProperty(
            name = "Scene Prefab",
            description = "Same content as 'Collective', but outputs a Urho3D xml scene (with Octree, PhysicsWorld and DebugRenderer)",
            default = True,
            update = update_func)

    sceneCreateZone : BoolProperty(
            name = "Create a default Zone",
            description = "Create DefaultZone-Node with -2000|-2000|-2000 2000|2000|2000",
            default = True,
            update = ExportNoGeo)

    sceneZoneCubeTexture : EnumProperty(
            name = "ZoneTexture",
            items = zone_cubetexture_items,
            update = ExportNoGeo)             

    sceneCreateSkybox : BoolProperty(
            name = "Creaete default skybox",
            description = "Create DefaultZone-Skybox(Models/Sphere.mdl)",
            default = False,
            update = ExportNoGeo)
    sceneSkyBoxHDR : BoolProperty(
            name = "HDR",
            description = "Use HDR-Material",
            update = ExportNoGeo,
            default = False)
    

    sceneSkyBoxCubeTexture : EnumProperty(
            name = "ZoneTexture",
            items = zone_cubetexture_items,
            update = ExportNoGeo)             

    trasfObjects : BoolProperty(
            name = "Transform objects",
            description = "Save objects position/rotation/scale, works only with 'Front View = Back'",
            default = True)

    export_userdata : BoolProperty(
            name = "Export Object Userdata",
            description = "Export the userdata of every object that have any specified in object-tab",
            default = True)

    physics : EnumProperty(
            name = "Physics",
            description = "Generate physics RigidBody(s) & Shape(s)",
            items = (('DISABLE', "No physics", "Do not create physics stuff"),
                        ('GLOBAL', "Global", "Create a unic RigidBody + Shape at the root. Expects a 'Physics.mdl' model as TriangleMesh."),
                        ('INDIVIDUAL', "Individual", "Create individual physics RigidBodies and Shapes")),
            default = 'DISABLE',
            update = update_func2)

    shapeItems = [ ('BOX', "Box", ""), ('CAPSULE', "Capsule", ""), ('CONE', "Cone", ""), \
                ('CONVEXHULL', "ConvexHull", ""), ('CYLINDER', "Cylinder", ""), ('SPHERE', "Sphere", ""), \
                ('STATICPLANE', "StaticPlane", ""), ('TRIANGLEMESH', "TriangleMesh", "") ]
    shape : EnumProperty(
            name = "CollisionShape",
            description = "CollisionShape type. Discarded if 'Collision Bounds' is checked in Physics panel.",
            items = shapeItems,
            default = 'TRIANGLEMESH',
            update = update_func2)

    meshnameDerivedBy : EnumProperty(
        name = "meshnameDerivedBy",
        description = "Meshname derived by",
        items=(('Object', "Object-Name", "The object's mesh gets the name of the node, which can result in duplicated meshes saved as different mesh-files"),
                ('Mesh', "Mesh-Name", "The object's mesh gets its name by the mesh preventing duplicated mesh-files")),
        default='Mesh')

    generateModelNamePrefix : BoolProperty(
        name ="add prefix to modelfiles",
        description="prefix 'scene_xxx_' to your model-filename",
        default=True
    )
        
    bonesGlobalOrigin : BoolProperty(name = "Bones global origin", default = False)
    actionsGlobalOrigin : BoolProperty(name = "Actions global origin", default = False)
    

# Reset settings button
class UrhoExportResetOperator(bpy.types.Operator):
    """ Reset export settings """

    bl_idname = "urho.exportreset"
    bl_label = "Revert settings to default"

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

    def execute(self, context):
        context.scene.urho_exportsettings.reset(context)
        return {'FINISHED'}


# Reset output paths button
class UrhoExportResetPathsOperator(bpy.types.Operator):
    """ Reset paths """

    bl_idname = "urho.exportresetpaths"
    bl_label = "Revert paths to default"

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

    def execute(self, context):
        context.scene.urho_exportsettings.reset_paths(context, True)
        return {'FINISHED'}


# View log button
class UrhoReportDialog(bpy.types.Operator):
    """ View export log """
    
    bl_idname = "urho.report"
    bl_label = "Urho export report"
 
    def execute(self, context):
        return {'FINISHED'}
 
    def invoke(self, context, event):
        global logMaxCount
        wm = context.window_manager
        addonPrefs = context.preferences.addons[__name__].preferences
        logMaxCount = addonPrefs.maxMessagesCount
        return wm.invoke_props_dialog(self, width = addonPrefs.reportWidth)
        #return wm.invoke_popup(self, width = addonPrefs.reportWidth)
     
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        for line in logList:
            lines = line.split(":", 1)
            if lines[0] == 'CRITICAL':
                lineicon = 'LIGHT'
            elif lines[0] == 'ERROR':
                lineicon = 'CANCEL'
            elif lines[0] == 'WARNING':
                lineicon = 'ERROR'
            elif lines[0] == 'INFO':
                lineicon = 'INFO'
            else:
                lineicon = 'TEXT'
            layout.label(text = lines[1], icon = lineicon)



# Export button
class UrhoExportOperator(bpy.types.Operator):
    """ Start exporting """
    
    bl_idname = "urho.export"
    bl_label = "Export"

    ignore_geo_skel_anim : bpy.props.BoolProperty(default=False)
    only_selected_mesh : bpy.props.BoolProperty(default=False)
  
    def execute(self, context):
        ExecuteAddon(context, not bpy.context.scene.urho_exportsettings.showLog, self.ignore_geo_skel_anim,self.only_selected_mesh)
        return {'FINISHED'}
 
    def invoke(self, context, event):
        return self.execute(context)

def CreateInitialMaterialTree(nodetree):
    if bpy.context.scene.urho_exportsettings.create_default_material_nodetree and nodetree and not nodetree.initialized and len(nodetree.nodes)==0:
        matNode = nodetree.nodes.new("urho3dmaterials__materialNode")
        matNode.location = Vector((0,200))

        techniqueNode = nodetree.nodes.new("urho3dmaterials__techniqueNode")
        techniqueNode.location = Vector((250,350))
        techniqueNode.prop_Technique = 'Techniques/NoTexture.xml'
        techniqueNode.width = 300

        standardNode = nodetree.nodes.new("urho3dmaterials__standardParams")
        standardNode.location = Vector((250,100))

        nodetree.links.new(matNode.outputs[0],techniqueNode.inputs[0])
        nodetree.links.new(matNode.outputs[0],standardNode.inputs[0])

    nodetree.initialized=True


def CreateMaterialFromNodetree(nodetree,material,pbr,copy_images=True):
    images=[]

    def add_filename_to_urhotexnode(urho3dTexNode,filename):
        categories = urho3dTexNode.customData['prop_Texture_cat']
        categories['all'].append((filename,filename,filename,CalcNodeHash(filename)))
        if "imported" not in categories:
            categories["imported"]=[]
        enum_id = CalcNodeHash(filename)
        categories['imported'].append((filename,filename,filename,enum_id))
        urho3dTexNode.prop_Texture=filename        

    def copy_image_and_set(eeveeTexNode,urho3dTexNode):
        image = eeveeTexNode.image

        settings = bpy.context.scene.urho_exportsettings
        # copy image from eevveeNode to Textures-Folder and add this image to the image-categories to be able to set it
        folder=os.path.join(settings.texturesPath,'')+"imported"
        filename=os.path.join(folder,'')+bpy.path.basename(image.filepath)
        abs_outputPath = os.path.join(bpy.path.abspath(settings.outputPath) ,'')

        if image.packed_file:
            full_ouput_path=abs_outputPath+filename
            image.save_render(full_ouput_path)
            add_filename_to_urhotexnode(urho3dTexNode,filename)
        else:
            ext = os.path.splitext(image.filepath)[1].lower()
            if ext==".png" or ext==".jpg" or ext==".dds":
                copy_file(image.filepath,abs_outputPath+folder,True)
                add_filename_to_urhotexnode(urho3dTexNode,filename)
            else:
                Path(+folder).mkdir(parents=True, exist_ok=True)
                withoutExt = os.path.splitext(filename)[0]
                img = Image.open(bpy.path.abspath(image.filepath),"r")
                
                new_resource_path = withoutExt+".png"
                full_output_path = abs_outputPath+new_resource_path
                img.save(full_output_path)
                add_filename_to_urhotexnode(urho3dTexNode,new_resource_path)
        

    def process_principled(bsdf):
        nonlocal images

        settings = bpy.context.scene.urho_exportsettings

        matNode = nodetree.nodes.new("urho3dmaterials__materialNode")
        matNode.location = Vector((0,200))

        techniqueNode = nodetree.nodes.new("urho3dmaterials__techniqueNode")
        techniqueNode.location = Vector((250,350))
        #techniqueNode.prop_Technique = 'Techniques/NoTexture.xml'
        techniqueNode.width = 500
        nodetree.links.new(matNode.outputs[0],techniqueNode.inputs[0])


        urho3d_color_tex   = None
        urho3d_normal_tex  = None
        urho3d_metallic_tex= None
        urho3d_rough_tex   = None
        urho3d_sepcular_tex= None

        base_color = (1,1,1,1)

        
        # base-color
        in_basecolor = bsdf.inputs["Base Color"]
        
        if in_basecolor.is_linked:
            basecol_node = in_basecolor.links[0].from_node
            
            if basecol_node.type=="TEX_IMAGE":
                # texture node
                urho3d_color_tex = nodetree.nodes.new("urho3dmaterials__textureNode")
                urho3d_color_tex.location = Vector((450,100))

                nodetree.links.new(matNode.outputs[0],urho3d_color_tex.inputs[0])                
                copy_image_and_set(basecol_node,urho3d_color_tex)
            else:
                print("Unknown basecolor_input:%s" %basecol_node.type)
                pass
        else:
            base_color = in_basecolor.default_value

        #normal
        in_normal = bsdf.inputs["Normal"]

        if in_normal.is_linked:
            normal_node = in_normal.links[0].from_node

            if normal_node.type=="NORMAL_MAP":
                in_normal_color = normal_node.inputs["Color"]
                if in_normal_color.is_linked and in_normal_color.links[0].from_node.type=="TEX_IMAGE":
                    normal_map_tex = in_normal_color.links[0].from_node

                    urho3d_normal_tex = nodetree.nodes.new("urho3dmaterials__textureNode")
                    urho3d_normal_tex.prop_unit='normal'
                    urho3d_normal_tex.location = Vector((650,100))
                    nodetree.links.new(matNode.outputs[0],urho3d_normal_tex.inputs[0])
                    copy_image_and_set(normal_map_tex,urho3d_normal_tex)

        # specular-color
        in_specularcolor = bsdf.inputs["Specular"]
        
        if in_specularcolor.is_linked:
            specular_node = in_specularcolor.links[0].from_node
            
            if specular_node.type=="TEX_IMAGE":
                # texture node
                urho3d_sepcular_tex = nodetree.nodes.new("urho3dmaterials__textureNode")
                urho3d_sepcular_tex.location = Vector((450,-200))
                urho3d_sepcular_tex.prop_unit='specular'
                nodetree.links.new(matNode.outputs[0],urho3d_sepcular_tex.inputs[0])                
                copy_image_and_set(specular_node,urho3d_sepcular_tex)
            else:
                print("Unknown basecolor_input:%s" %basecol_node.type)
                pass
        else:
            base_color = in_basecolor.default_value


        # rough / metallic

        rough_image = None
        rough_channel = None
        metal_image = None
        metal_channel = None
        composition_size = (0,0)
        outputfilename = ""



        in_rough = bsdf.inputs["Roughness"]
        if in_rough.is_linked:
            rough_node = in_rough.links[0].from_node

            if rough_node.type=="SEPRGB":
                rough_channel = in_rough.links[0].from_socket.name

                in_rough_image = rough_node.inputs["Image"]

                if in_rough_image.is_linked:
                    rough_image_node = in_rough_image.links[0].from_node
            else:
                rough_image_node = rough_node # maybe they connect the texture directly

            if rough_image_node.type=="TEX_IMAGE":
                rough_image = Image.open(bpy.path.abspath(rough_image_node.image.filepath),"r")
                if rough_image:
                    composition_size = (rough_image.width,rough_image.height)
                outputfilename += os.path.splitext(bpy.path.basename(rough_image_node.image.filepath))[0]
            else:
                print("Unknown rough-image-node:%s" %rough_image.type)
                pass                        

        in_metallic = bsdf.inputs["Metallic"]
        if in_metallic.is_linked:
            metallic_node = in_metallic.links[0].from_node

            if metallic_node.type=="SEPRGB":
                metal_channel = in_metallic.links[0].from_socket.name

                in_metal_image = rough_node.inputs["Image"]

                if in_metal_image.is_linked:
                    metal_image_node = in_metal_image.links[0].from_node
            else:
                metal_image_node=metallic_node # maybe they connect the texture directly

            if metal_image_node.type=="TEX_IMAGE":
                metal_image = Image.open(bpy.path.abspath(metal_image_node.image.filepath),"r")
                if metal_image.width > composition_size[0]:
                    composition_size=(metal_image.width,metal_image.height)
                
                part2 = os.path.splitext(bpy.path.basename(metal_image_node.image.filepath))[0]
                if outputfilename!=part2:
                    outputfilename+=part2 # only had 2nd part if both parts are from different files
            else:
                print("Unknown rough-image-node:%s" %rough_image.type)
                pass                        

        metallicroughness = rough_image or metal_image

        if metallicroughness:
            empty_image = Image.new("RGBA",composition_size,(0,0,0,255))
            r,g,b,a = empty_image.split()

            if rough_image:
                if rough_image.width < composition_size[0] or rough_image.height < composition_size[1]:
                    rough_image = rough_image.resize(composition_size)
                r = rough_image.getchannel(rough_channel)

            if metal_image:
                if metal_image.width < composition_size[0] or metal_image.height < composition_size[1]:
                    metal_image = metal_image.resize(composition_size)
                b = metal_image.getchannel(metal_channel)

            result = Image.merge("RGBA",(r,g,b,a))

            resource_part = os.path.join(settings.texturesPath,'')+"imported/gen_rm_"+outputfilename+".png"
            outputfile=os.path.join( bpy.path.abspath(settings.outputPath),'')+resource_part
            result.save(outputfile)

            urho3d_roughmetal_tex = nodetree.nodes.new("urho3dmaterials__textureNode")
            urho3d_roughmetal_tex.prop_unit='specular'
            urho3d_roughmetal_tex.location = Vector((850,100))
            nodetree.links.new(matNode.outputs[0],urho3d_roughmetal_tex.inputs[0])

            add_filename_to_urhotexnode(urho3d_roughmetal_tex,resource_part)

        if pbr:
            pbsNode = nodetree.nodes.new("urho3dmaterials__pbsParams")
            pbsNode.prop_MatDiffColor=base_color
            pbsNode.location = Vector((250,100))

            nodetree.links.new(matNode.outputs[0],pbsNode.inputs[0])
        else:
            standardNode = nodetree.nodes.new("urho3dmaterials__standardParams")
            standardNode.location = Vector((250,100))
            nodetree.links.new(matNode.outputs[0],standardNode.inputs[0])




        nodetree.initialized=True
        






    if nodetree and material and material.node_tree:
        found_bsdf = False
        for node in material.node_tree.nodes:
            if node.type=="BSDF_PRINCIPLED":
                if found_bsdf:
                    print("ERROR! multiple bsdf-nodes not supported") # is that even allowed on the blender side?
                    break
                process_principled(node)
                found_bsdf = True
                

class UrhoExportMaterialsOnlyOperator(bpy.types.Operator):
    """ Start exporting """
    
    bl_idname = "urho.exportmaterials"
    bl_label = "Export Materials only"
  
    def execute(self, context):
        ExecuteUrhoExportMaterialsOnly(context)
        return {'FINISHED'}
 
    def invoke(self, context, event):
        return self.execute(context)

# Export without report window
class UrhoExportCommandOperator(bpy.types.Operator):
    """ Start exporting """
    
    bl_idname = "urho.exportcommand"
    bl_label = "Export command"
  
    def execute(self, context):
        ExecuteAddon(context, silent=True, ignoreGeoAnim=True)
        return {'FINISHED'}
 
    def invoke(self, context, event):
        return self.execute(context)

class UrhoExportSelectLodMesh(bpy.types.Operator):
    """ select mesh """

    bl_idname = "urho.selectmesh"
    bl_label = "Select mesh"
  
    meshname : bpy.props.StringProperty(default="")

    def execute(self, context):
        if self.meshname and self.meshname!="":
            context.object.data=bpy.data.meshes[self.meshname]
        return {'FINISHED'}
 
    def invoke(self, context, event):
        return self.execute(context)    


class UrhoApplyVertexData(bpy.types.Operator):
    ''' Start runtime '''
    bl_idname = "urho.apply_vertexdata"
    bl_label = "Apply"
    

    apply_to_selected : bpy.props.BoolProperty()

    @classmethod
    def poll(self, context):
        return context.object.type=="MESH"

    def execute(self,context):
        objs = None


        me = context.object

        if self.apply_to_selected:
            objs = bpy.context.selected_objects
        else:
            objs = bpy.context.scene.objects

        for obj in objs:
            if obj == me or obj.type!="MESH":
                continue
            # set values
            me.data.urho_export.copyInto(obj.data.urho_export) 

        return {'FINISHED'}





# Start runtime
class UrhoExportStartRuntime(bpy.types.Operator):
    ''' Start runtime '''
    bl_idname = "urho.start_runtime"
    bl_label = "Start Runtime"
    


    @classmethod
    def poll(self, context):
        return True

    def execute(self, context):
        scene = context.scene
        settings = scene.urho_exportsettings
        addonPrefs = bpy.context.preferences.addons[__name__].preferences

        execpath = bpy.path.abspath(addonPrefs.runtimeFile)
        workingdir =os.path.dirname(execpath)
        # if execpath[0:2] in { "./", ".\\" }:
        #     pwd = os.path.dirname(bpy.app.binary_path)
        #     execpath = pwd + os.sep + execpath

        # workingdir = bpy.path.abspath(settings.outputPath)
        # # workingdir = bpy.path.abspath(settings.runtimeWorkingDir)



        processParams = []
        processParams.append(execpath)

        
##        parameters = " --workdir "+workingdir
        print("EXEC-DIR: %s" % execpath)
        print("PWD:%s abspath:%s" % ( os.path.dirname(bpy.app.binary_path),bpy.path.abspath(addonPrefs.runtimeFile) ))
        # print("WORKING-DIR: %s" % workingdir)
        # print("PARAMS:%s" % processParams)
        # launch game
        try:
            subp = subprocess.Popen(processParams,  shell=False, cwd=workingdir)
            print("\nLAUNCH RUNTIME: %s\n" % processParams)
            # if settings.runtimeBlocking:
            #     subp.communicate() #like wait() but without the risk of deadlock with verbose output
            returnv = subp.returncode

            if returnv != 0:
                self.report({'ERROR'},"runtime exited anormally.")
                return {'CANCELLED'}

            self.report({'INFO'},"runtime exited normally.")
        except OSError as er:
            self.report({'ERROR'}, "Could not launch: " + execpath + " Error: " + str(er))
            return {'CANCELLED'}

        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)

## TODO: mrege both into one...
class UrhoExportStartRuntime2(bpy.types.Operator):
    ''' Start runtime '''
    bl_idname = "urho.start_runtime2"
    bl_label = "Start Runtime 2"
    

    @classmethod
    def poll(self, context):
        return True

    def execute(self, context):
        scene = context.scene
        settings = scene.urho_exportsettings


        execpath = bpy.path.abspath(settings.runtime2File)
        if execpath[0:2] in { "./", ".\\" }:
            pwd = os.path.dirname(bpy.app.binary_path)
            execpath = pwd + os.sep + execpath

        workingdir =os.path.dirname(execpath)

    
        # # workingdir = bpy.path.abspath(settings.runtimeWorkingDir)

        processParams = []
        processParams.append(execpath)
##        parameters = " --workdir "+workingdir
        print("EXEC-DIR: %s" % execpath)
        # print("WORKING-DIR: %s" % workingdir)
        # print("PARAMS:%s" % processParams)
        # launch game
        try:
            subp = subprocess.Popen(processParams,  shell=False, cwd=workingdir)
            print("\nLAUNCH RUNTIME: %s\n" % processParams)
            # if settings.runtimeBlocking:
            #     subp.communicate() #like wait() but without the risk of deadlock with verbose output
            returnv = subp.returncode

            if returnv != 0:
                self.report({'ERROR'},"runtime exited anormally.")
                return {'CANCELLED'}

            self.report({'INFO'},"runtime exited normally.")
        except OSError as er:
            self.report({'ERROR'}, "Could not launch: " + execpath + " Error: " + str(er))
            return {'CANCELLED'}

        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)


class ApplyExportUrhoToCollectionChildren(bpy.types.Operator):
    ''' Batch (un)set direct(!) children of this collection (exclusive parent) '''
    bl_idname = "urho.colexport_apply_children"
    bl_label = "Apply to Children"
    
    exportValue : bpy.props.BoolProperty()

    @classmethod
    def poll(self, context):
        return True

    # def iterate_collection(self,collection,value):
    #     if not collection or len(collection.children)==0:
    #         return
        
    #     collection.urhoExport = value

    #     for col in collection.children:
    #         col.urhoExport = value
    #         self.iterate_collection(col,value)



    def execute(self, context):

        parent_col = bpy.context.collection

        if not parent_col:
            return

        for child in parent_col.children:
            child.urhoExport=self.exportValue

        return {'FINISHED'}

class PackOutputFolder(bpy.types.Operator):
    ''' Use packagetool on output-folder '''
    bl_idname = "urho.pack_exportfolder"
    bl_label = "Pack Folder"
    

    @classmethod
    def poll(self, context):
        return True

    def execute(self, context):
        settings = context.scene.urho_exportsettings
        data={}
        data["package_folder"]=bpy.path.abspath(settings.outputPath)
        data["package_name"]=bpy.path.abspath(settings.packPath)

        PublishAction(self,context,"packagetool",data)

        return {'FINISHED'}

class UrhoCreateNodetreeFromMaterial(bpy.types.Operator):
    ''' Tries to create Urho3D-Material from eevee-material '''
    bl_idname = "urho.createnodetree_from_material"
    bl_label = "Create Urho3D-Material from Blender-Material"
    
    nodetreeName : bpy.props.StringProperty()

    @classmethod
    def poll(self, context):
        return True

    def execute(self, context):
        settings = context.scene.urho_exportsettings
        
        if settings.create_nodetree_from_material and self.nodetreeName:
            material = bpy.data.materials[settings.create_nodetree_from_material]
            nodetree = bpy.data.node_groups[self.nodetreeName]
            CreateMaterialFromNodetree(nodetree,material,True)

        return {'FINISHED'}


def ObjectUserData(obj,layout):
    box = layout.box()
    box.label(text="Userdata / Tags")
    userDataAmount = len(obj.user_data)
    if userDataAmount>0:
        row = box.label(text="Object Userdata")
        row = box.row()
        row.template_list("UL_URHO_LIST_USERDATA", "The_List", obj,
                        "user_data", obj, "list_index_userdata",rows=userDataAmount+1,maxrows=6)            
    else:
        row = box.box().row()
        row.label(text="none")


    row = box.row()
    row.operator('urho_keyvalue.new_item', text='NEW')
    row.operator('urho_keyvalue.delete_item', text='REMOVE')
    row.operator('urho_keyvalue.move_item', icon="TRIA_UP",text='').direction = 'UP'
    row.operator('urho_keyvalue.move_item', icon="TRIA_DOWN",text='').direction = 'DOWN'


class UrhoExportMaterialPanel(bpy.types.Panel):
    bl_idname = "urho.exportmaterialpanel"
    bl_label = "Urho export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    
    @classmethod
    def poll(self, context):
        return  bpy.context.scene.render.engine=="URHO3D"

        
    # Draw the export panel
    def draw(self, context):
        layout = self.layout
        obj = context.object

        if obj and obj.type=="MESH":
            ObjectMaterialNodetree(obj, layout)
            



# The export panel, here we draw the panel using properties we have created earlier
class UrhoExportObjectPanel(bpy.types.Panel):
    bl_idname = "urho.exportobjectpanel"
    bl_label = "Urho export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    #bl_options = {'DEFAULT_CLOSED'}
    
    # Draw the export panel
    def draw(self, context):
        layout = self.layout
        obj = context.object


        currentCollection = bpy.context.collection
        if currentCollection:
            box = layout.box()
            box.label(text="Collection '%s'" % currentCollection.name)
            row = box.row()
            row.prop(currentCollection,"urhoExport",text="export as urho object")
            row = box.row()
            row.prop(currentCollection,"instance_offset",text="Offset")
            
            if len(currentCollection.children)>0:
                row = box.row()
                #,description="Batch unset direct(!) children of this collection (exclusive parent)"
                row.operator("urho.colexport_apply_children",text="children: set export",icon="CHECKBOX_HLT").exportValue=True
                row = box.row()
                # ,description="Batch unset direct(!) children of this collection (exclusive parent)"
                row.operator("urho.colexport_apply_children",text="children: unset export",icon="CHECKBOX_DEHLT").exportValue=False


        if obj.type=="MESH":
            box = layout.box()
            
            row = box.row()
            row.label(text="Shadow Settings")
            row = box.row()
            row.prop(obj,"cast_shadow")
        # row = box.row()
        # row.prop(obj,"receive_shadow")


        ObjectComponentSubpanel(obj,layout,layout,False)

        ObjectUserData(obj,layout)
        #row.prop(object,"exportNoMesh",text="NO mesh-export for object")


def MeshUI(self,context):
    layout = self.layout
    obj = context.object

    scene = context.scene
    settings = scene.urho_exportsettings

    mesh = obj.data
    row = layout.row()
    row.label(text="Export Vertex-Data:")
    row = layout.row()
    row.prop(mesh.urho_export,"export_pos",text="Position")
    row.prop(mesh.urho_export,"export_norm",text="Normals")
    row = layout.row()
    col = row.column()
    col.prop(mesh.urho_export,"export_tan",text="Tangent")
    col.enabled = mesh.urho_export.export_uv and mesh.urho_export.export_norm and mesh.urho_export.export_pos
    row.prop(mesh.urho_export,"export_vcol",text="Vertex Color")
    row = layout.row()
    row.prop(mesh.urho_export,"export_weight",text="Weights")
    row.prop(mesh.urho_export,"export_morph",text="Morphs")
    
    row = layout.row()
    row.prop(mesh.urho_export,"export_uv",text="UV")
    box = row.box()
    if len(bpy.context.selected_objects)>0:
        box.operator("urho.apply_vertexdata",text="Apply to selected").apply_to_selected=True
    else:
        box.operator("urho.apply_vertexdata",text="Apply to all").apply_to_selected=False

    if mesh.urho_export.export_uv:

        box = layout.box()

        row = box.row()
        row.prop(mesh.urho_export,"active_uv_as_uv1",text="use active uvmap as uv1")

        row = box.row()
        if mesh.urho_export.active_uv_as_uv1:
            row.prop(mesh.urho_export,"auto_uv1_idx",text="uv1")
        else:
            row.prop(mesh.urho_export,"manual_uv1_idx",text="uv1")

        row = box.row()
        row.prop(mesh.urho_export,"use_uv2",text="use uv2")
        if mesh.urho_export.use_uv2:
            row.prop(mesh.urho_export,"manual_uv2_idx",text="")

    box = layout.box()
    row = box.row()
    row.prop_search(obj,"lodsetName",bpy.data.worlds[0],"lodsets")
    row = box.row()
    row.operator("urho_button.generic",text="new lodset").typeName="create_lodset"

    lodset = getLodSetWithID(obj.lodsetID)

    if lodset:
        row.operator("urho_button.generic",text="DELETE current").typeName="delete_lodset"
    

    if lodset:
        row = box.row()
        row.prop(lodset,"name")
        row = box.row();
        row = box.label(text="Lods")
        row = box.row()
        row.template_list("UL_URHO_LIST_LOD", "The_List", lodset,
                        "lods", lodset, "lods_idx",rows=len(lodset.lods))

        row = box.row()
        row.prop(lodset,"armatureObj")
        row = box.row()
        row.operator('urho_lod.new_item', text='NEW')
        row.operator('urho_lod.delete_item', text='REMOVE')
        row.operator('urho_lod.move_item', text='UP').direction = 'UP'
        row.operator('urho_lod.move_item', text='DOWN').direction = 'DOWN'


# The export panel, here we draw the panel using properties we have created earlier
class UrhoExportMeshPanel(bpy.types.Panel):
    bl_idname = "urho.exportmeshpanel"
    bl_label = "Urho export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    #bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(self, context):
        return context.object.type=="MESH" or context.object.type=="LIGHT"


    # Draw the export panel
    def draw(self, context):
        layout = self.layout
        obj = context.object

        scene = context.scene
        settings = scene.urho_exportsettings

        if context.object.type=="LIGHT":
            light = obj.data
            row = layout.row()
            box = row.box()
            box.prop(light,"use_pbr",text="Use Physical Values(PBR)")

        elif context.object.type=="MESH":
            MeshUI(self,context)
        
# The export panel, here we draw the panel using properties we have created earlier
class UrhoExportScenePanel(bpy.types.Panel):
    
    bl_idname = "urho.exportscenepanel"
    bl_label = "Urho export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    #bl_options = {'DEFAULT_CLOSED'}
    
    # Draw the export panel
    def draw(self, context):
        layout = self.layout
        obj = context.object

        box = layout.box()
        row = box.label(text="Userdata")
        row = box.row()
        row.prop(bpy.context.scene,"nodetree",text="Scene logic")


# The export panel, here we draw the panel using properties we have created earlier
class UrhoExportRenderPanel(bpy.types.Panel):
    
    bl_idname = "urho.exportrenderpanel"
    bl_label = "Urho export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    #bl_options = {'DEFAULT_CLOSED'}
    
    # Draw the export panel
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.urho_exportsettings

        outer_row = layout.row()
        #row=layout.row(align=True)
        minimizeIcon = 'ZOOM_IN' if settings.minimize else 'ZOOM_OUT'
        outer_row.prop(settings, "minimize", text="", icon=minimizeIcon, toggle=False)
        
        col = outer_row.column()
        row = col.row()
        op = row.operator("urho.export", icon='EXPORT',text='Export: ALL SCENE')
        op.ignore_geo_skel_anim=False
        op.only_selected_mesh=False
        row = col.row()
        op = row.operator("urho.export", icon='EXPORT',text='Export: WITHOUT GEOMETRY')
        op.ignore_geo_skel_anim=True
        op.only_selected_mesh=False
        row = col.row()
        op = row.operator("urho.export", icon='EXPORT',text='Export: SELECTED MESHES')
        op.ignore_geo_skel_anim=False
        op.only_selected_mesh=True
        row = col.row()
        row.operator("urho.exportmaterials", icon='EXPORT', text='Export: ONLY MATERIAL')



        row = col.row()
        split = row.split(factor=0.2)
        split.column().label(text="Folder:")
        split = split.split()
        split.column().prop(settings, "outputPath")

        row = col.row()
        row.prop(settings, "exportOnSave")
        if settings.exportOnSave:
            row.prop(settings,"exportOnSaveMode",text="")

        #split = layout.split(percentage=0.1)
        if sys.platform.startswith('win'):
            outer_row.operator("wm.console_toggle", text="", icon='CONSOLE')
        outer_row.prop(settings, "onlyErrors", text="", icon='FORCE_WIND')
        outer_row.operator("urho.report", text="", icon='TEXT')
        if settings.minimize:
            return

        # row = layout.row()
        # row.operator("urho.export", icon='EXPORT',text='EXPORT(no geo)').ignore_geo_skel_anim=True
        # row.operator("urho.exportmaterials", icon='EXPORT')
        
        row = layout.row()



        row.separator()
        row.separator()
        row.prop(settings,"runtimeAutoUpdateTransforms",text="Export on transform")
        row.prop(settings,"showLog")    


        box = layout.box()
        
        ibox = box.box()
        row = ibox.row()
        row.prop(settings,"generateSceneHeader")
        if settings.generateSceneHeader:
            row = ibox.row()
            row.prop(settings,"sceneHeaderOutputPath")

        ibox = box.box()
        row = ibox.row()
        split = row.split(factor=0.7)
        col = split.column()
        col.label(text="Pack Destination:")
        split = split.split()
        col = split.column()
        pack_op = col.operator("urho.pack_exportfolder")
        col.enabled=settings.packPath!=""
        ibox.prop(settings,"packPath")

        row = box.row()
        row.label(text="Modelname:")
        row.prop(settings, "meshnameDerivedBy", expand=True)

        box.prop(settings, "generateModelNamePrefix")

        box.prop(settings, "fileOverwrite")
        row = box.row()
        row.prop(settings, "useSubDirs")
        showDirsIcon = 'ZOOM_OUT' if settings.showDirs else 'ZOOM_IN'
        if settings.showDirs:
            subrow = row.row(align=True)
            subrow.prop(settings, "addDir", text="", icon='TRIA_DOWN_BAR')
            subrow.prop(settings, "removeDir", text="", icon='TRIA_UP_BAR')
            subrow.prop(settings, "addSceneDir", text="", icon='GROUP')
            subrow.operator("urho.exportresetpaths", text="", icon='LIBRARY_DATA_DIRECT')

        row.prop(settings, "showDirs", text="", icon=showDirsIcon, toggle=False)
        if settings.showDirs:
            dbox = box.box()
            dbox.prop(settings, "modelsPath")
            dbox.prop(settings, "animationsPath")
            dbox.prop(settings, "materialsPath")
            dbox.prop(settings, "techniquesPath")
            dbox.prop(settings, "texturesPath")
            dbox.prop(settings, "objectsPath")
            dbox.prop(settings, "scenesPath")

        if (True):
            box = layout.box()
            row = box.row()

            addonPrefs = bpy.context.preferences.addons[__name__].preferences

            row.prop(addonPrefs,"runtimeFile")
            # row = box.row()
            # row.prop(settings,"runtimeWorkingDir",text="additional resource-dir")
            # row = box.row()
            # row.prop(settings,"runtimeFlags")            
            row = box.row()
            row.operator("urho.start_runtime",icon="GHOST_ENABLED")

            row = box.row()
            row.prop(settings,"enableRuntime2")
            if (settings.enableRuntime2):
                row = box.row()
                row.prop(settings,"runtime2File")
                if (settings.runtime2File):
                    path = bpy.path.abspath(settings.runtime2File)
                    if os.path.exists(path):
                        filename = ntpath.basename(path)
                        row = box.row()
                        row.operator("urho.start_runtime2",text="Run %s" % filename)


            # if IsJsonNodeAddonAvailable:
            #     row.prop(bpy.data.worlds[0].jsonNodes,"path",text="material-json path")  
            # else:
            #     row.prop(settings,"runtimeExportComponents",text="material-json path")  
            
            innerbox = box.box()
            row = innerbox.row()
            row.prop(settings,"runtimeShowPhysics",text="show physics")
            if settings.runtimeShowPhysics:
                row.prop(settings,"runtimeShowPhysicsDepth",text="use depth test")

            row = innerbox.row()
            row.prop(settings,"runtimeExportComponents")
            if settings.runtimeExportComponents:
                row.prop(settings,"runtimeExportComponentsMode",text="")

            row = innerbox.row()
            row.prop(settings,"runtimeRenderPath")

            #row = innerbox.row()
            #row.prop(settings,"runtimeActivatePhysics",text="activate physics")
            



        row = layout.row()
        row.label(text="Settings:")
        row.operator("urho.exportreset", text="", icon='LIBRARY_DATA_DIRECT')
        
        box = layout.box()

        row = box.row()
        row.label(text="Objects:")
        row.prop(settings, "source", expand=True)

        # row = box.row()
        # row.label(text="Origin:")
        # row.prop(settings, "origin", expand=True)

        box.prop(settings, "orientation")

        #        # box.prop(settings, "merge")
        # if settings.merge:
        #     row = box.row()
        #     row.separator()
        #     row.prop(settings, "mergeNotMaterials")        # box.prop(settings, "merge")
        # if settings.merge:
        #     row = box.row()
        #     row.separator()
        #     row.prop(settings, "mergeNotMaterials")

        #box.prop(settings, "scale")
        
        box.prop(settings, "modifiers")
        
        # if settings.modifiers:
        #     row = box.row()
        #     row.separator()
        #     row.prop(settings, "modifiersRes", expand=True)

        # TODO
        # box.prop(settings, "merge")
        # if settings.merge:
        #     row = box.row()
        #     row.separator()
        #     row.prop(settings, "mergeNotMaterials")

        box.prop(settings,"ignoreHidden")
        box.prop(settings, "exportGroupsAsObject")
        box.prop(settings, "exportObjectCollectionAsTag")
        box.prop(settings,"wiredAsEmpty")

        row = box.row()
        row.prop(settings, "selectErrors")
        row.prop(settings, "errorsEnum")
        
        box.prop(settings, "forceElements")

        #TODO: what and why
        #box.prop(settings, "geometrySplit")
        box.prop(settings, "optimizeIndices")
        box.prop(settings, "lods")
        if settings.lods:
            row = box.row()
            row.separator()
            row.prop(settings, "strictLods")

        box = layout.box()

        row = box.row()
        row.prop(settings, "skeletons")
        row.label(text="", icon='BONE_DATA')
        if settings.skeletons:
            row = box.row()
            row.separator()
            col = row.column()
            col.prop(settings, "derigify")
            #col.prop(settings, "bonesGlobalOrigin")
            #col.prop(settings, "actionsGlobalOrigin")
            col.prop(settings, "onlyDeformBones")
            col.prop(settings, "onlyVisibleBones")
            col.prop(settings, "parentBoneSkinning")
            col.prop(settings, "clampBoundingBox")

        row = box.row()
        column = row.column()
        column.enabled = settings.skeletons
        column.prop(settings, "animations")
        column = row.column()
        column.enabled = not settings.skeletons
        column.prop(settings, "objAnimations")
        row.label(text="", icon='ANIM_DATA')
        if (settings.skeletons and settings.animations) or settings.objAnimations:
            row = box.row()
            row.separator()
            column = row.column()
            column.prop(settings, "animationSource")
            column.prop(settings, "animationExtraFrame")
            column.prop(settings, "animationTriggers")
            if settings.animationTriggers:
                row = column.row()
                row.separator()
                row.prop(settings, "animationRatioTriggers")
            if settings.animations:
                column.prop(settings, "onlyKeyedBones")
            col = column.row()
            col.enabled = 'ACTION' in settings.animationSource
            col.prop(settings, "actionsByFcurves")
            row = column.row()
            row.prop(settings, "animationPos")
            row.prop(settings, "animationRot")
            row.prop(settings, "animationSca")
            column.prop(settings, "filterSingleKeyFrames")
        
        row = box.row()
        row.prop(settings, "geometries")
        row.label(text="", icon='MESH_DATA')
        if settings.geometries:
            row = box.row()
            row.label(text="hint: vertex data set on mesh-panel")
            row.enabled=False
        #     row.separator()
        #     row.prop(settings, "geometryPos")
        #     row.prop(settings, "geometryNor")
            
        #     row = box.row()
        #     row.separator()
        #     row.prop(settings, "geometryUV")
        #     row.prop(settings, "geometryUV2")

        #     row = box.row()
        #     row.separator()
        #     col = row.column()
        #     col.enabled = settings.geometryPos and settings.geometryNor and settings.geometryUV
        #     col.prop(settings, "geometryTan")
        #     col = row.column()
        #     col.enabled = settings.skeletons
        #     col.prop(settings, "geometryWei")
            
        #     row = box.row()
        #     row.separator()
        #     row.prop(settings, "geometryCol")
        #     row.prop(settings, "geometryColAlpha")
        
        row = box.row()
        row.enabled = settings.geometries
        row.prop(settings, "morphs")
        row.label(text="", icon='SHAPEKEY_DATA')
        if settings.geometries and settings.morphs:
            row = box.row()
            row.separator()
            col = row.column()
            col.enabled = settings.geometryNor
            col.prop(settings, "morphNor")
            col = row.column()
            col.enabled = settings.morphNor and settings.geometryTan
            col.prop(settings, "morphTan")

        # TODO
        # row = box.row()
        # row.prop(settings, "materials")
        # row.label(text="", icon='MATERIAL_DATA')
        # if settings.materials:
        #     row = box.row()
        #     row.separator()
        #     row.prop(settings, "materialsList")

        #row = box.row()
        #row.prop(settings, "textures")
        #row.label(text="", icon='TEXTURE_DATA')

        row = box.row()
        row.prop(settings, "prefabs")
        row.label(text="", icon='MOD_OCEAN')

        if settings.prefabs:
            row = box.row()
            row.separator()
            row.prop(settings, "individualPrefab")

            row.label(text="", icon='MOD_BUILD')

            if (settings.individualPrefab):
                row = box.row()
                row.separator()
                row.separator()
                row.prop(settings, "individualPrefab_onlyRootObject")



            if not settings.merge:
                row = box.row()
                row.separator()
                row.prop(settings, "collectivePrefab")
                row.label(text="", icon='URL')

            row = box.row()
            row.separator()
            row.prop(settings, "scenePrefab")
            row.label(text="", icon='WORLD')

            # if settings.scenePrefab:
            #     row = box.row()
            #     row.prop(settings,"sceneCreateZone")


            specialBox = box.box()
            row = specialBox.row()
            row.prop(settings, "trasfObjects")

            row = specialBox.row()
            row.prop(settings, "export_userdata")

            row = specialBox.row()
            row.prop(settings, "runtimeUnstable")
            


            # row = specialBox.row()
            # # todo: make it possible to check if physics are used in component-nodes and otherwise take the default settings(!)
            # row.label(text="default physics settings are ignored for objects with component-nodes")

            # row = specialBox.row()
            # row.prop(settings, "physics")
            # row.label(text="", icon='PHYSICS')

            # row = specialBox.row()
            # row.prop(settings, "shape")
            # row.label(text="", icon='GROUP')


def ObjectComponentSubpanel(obj,layout,currentLayout=None, showAutoSelect=True):
    if not layout or not obj: 
        return
    
    if not currentLayout:
        currentLayout = layout

    ## object's nodetree-managment
    box = currentLayout.box()
    row = box.label(text="Component Nodetrees")

    row = box.row()

    if len(obj.nodetrees)>0:
        row = box.row()
        row.template_list("UL_URHO_LIST_NODETREE", "The_List", obj,
                        "nodetrees", obj, "list_index_nodetrees",rows=len(obj.nodetrees)+1)
    else:
        row = box.box()
        row.label(text="none")

    row = box.row()
    row.operator('urho_nodetrees.new_item', text='Add')
    row.operator('urho_nodetrees.delete_item', text='Del')
    row.operator('urho_nodetrees.move_item', icon="TRIA_UP",text='').direction = 'UP'
    row.operator('urho_nodetrees.move_item', icon="TRIA_DOWN",text='').direction = 'DOWN'
    if showAutoSelect:
        row = box.row()
        row.prop(bpy.data.worlds[0].jsonNodes,"autoSelectObjectNodetree",text="autoselect object-nodetree")

def ObjectMaterialNodetree(obj,box):
    box = box.box()
    row = box.row()
    row.label(text="Material Nodetrees")
    #row.prop(bpy.context.active_object.data,"materialNodetree")
    row = box.row()
    row.template_list("UL_URHO_LIST_MATERIAL_NODETREE", "The_material_List", obj.data,
    "materialNodetrees", obj, "active_material_index",rows=len(obj.data.materialNodetrees)+1)

    row = box.row()
    row.operator('urho_material_nodetrees.new_item', text='NEW')
    row.operator('urho_material_nodetrees.delete_item', text='REMOVE')
    # no movement of the materialtree-slots, as I dont know how to stabely swap the change in the mesh
    # maybe using blender's material operators: 
    #row.operator("object.material_slot_move", icon='TRIA_UP', text="").direction = 'UP'
    #row.operator("object.material_slot_move", icon='TRIA_DOWN', text="").direction = 'DOWN'                


    #row.operator('urho_material_nodetrees.move_item', text='UP').direction = 'UP'
    #row.operator('urho_material_nodetrees.move_item', text='DOWN').direction = 'DOWN'

    #bpy.ops.wm.read_homefile('INVOKE_DEFAULT')                
    row = box.row()
    row.prop(bpy.data.worlds[0].jsonNodes,"autoSelectObjectNodetree",text="autoselect object-nodetree")

    if obj.mode == 'EDIT':
        row = box.row(align=True)
        row.operator("object.material_slot_assign", text="Assign")
        row.operator("object.material_slot_select", text="Select")
        row.operator("object.material_slot_deselect", text="Deselect")                


class UrhoExportNodetreePanel(bpy.types.Panel):
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_label = "Urho3d-Nodetree"
    bl_category = "Urho3D"
#    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        if bpy.context.active_object:
            obj = bpy.context.active_object

            space_treetype = bpy.context.space_data.tree_type
            nodetree = bpy.context.space_data.node_tree
            settings = bpy.context.scene.urho_exportsettings

            #print("TreeType:%s" % space_treetype )
            PingForRuntime()

            layout = self.layout
            box = layout.box()
            row = box.label(text="Nodetrees:")

            innerBox = box.box()
            row = innerBox.row()
            row.prop(bpy.context.scene,"nodetree",text="Scene-Logic")


            if space_treetype=="urho3dcomponents":
                ObjectComponentSubpanel(obj,layout,box)

            if space_treetype=="urho3dmaterials" and bpy.context.active_object.type=="MESH":
                innerBox = box.box()
                row = innerBox.row()
                row.prop(settings,"create_default_material_nodetree",text="auto-create nodetree for empty nodetrees")
                if nodetree and len(bpy.context.selected_objects):
                    row = innerBox.row()
                    row.operator("urho_nodetrees.set_selected").material_nt_name=nodetree.name


                ObjectMaterialNodetree(obj,box)

                if nodetree and not nodetree.initialized:
                    #print("TRY TO INIT")

                    def QueuedExecution():
                        CreateInitialMaterialTree(nodetree)
                        return

                    execution_queue.execute_or_queue_action(QueuedExecution)

            jsonNodes = bpy.data.worlds[0].jsonNodes

            row = layout.row()        
            row.prop(jsonNodes,"autoSelectObjectNodetree",text="autoselect object nodetree")

            if nodetree and settings.runtimeUnstable:
                row = layout.row()
                row.label(text="Experimental")
                innerBox = layout.box()
                row = innerBox.row()
                row.label(text="Create Nodes from Material:")
                
                row = innerBox.row()
                row.prop_search(settings,"create_nodetree_from_material",bpy.data,"materials",text="")
                row = innerBox.row()
                op = row.operator("urho.createnodetree_from_material")
                op.nodetreeName = nodetree.name




class URHO_PT_mainscene(bpy.types.Panel):
    bl_idname = "URHO_PT_MAINSCENE"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Urho3D"
    bl_label ="Urho3D-Scene"

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        settings = bpy.context.scene.urho_exportsettings

        layout = self.layout

        row = layout.row()
        box = layout.box()
        row = box.row()
        row.prop(settings,"runtimeRenderPath")
        
        if settings.runtimeUnstable:
            row = box.row()
            #row.prop(settings,"runtimeShowSRGB")
            row.prop(settings,"runtimeUseGamma")
            row.prop(settings,"runtimeUseHDR")
            #row = box.row()
            row.prop(settings,"runtimeUseBloom")
            row.prop(settings,"runtimeUseFXAA2")
        

            row = layout.row()
            row.prop(bpy.context.scene,"nodetree",text="Scene logic")

        if settings.scenePrefab:
            #Zone
            row = layout.row()
            split = row.split(factor=0.25)
            split.prop(settings,"sceneCreateZone",text="Zone")
            split=split.split(factor=0.75)
            if settings.sceneCreateZone:
                split.prop(settings,"sceneZoneCubeTexture",text="Texture")

            #Skybox
            row = layout.row()
            split = row.split(factor=0.25)
            split.prop(settings,"sceneCreateSkybox",text="Skybox")
            split=split.split(factor=0.75)
            if settings.sceneCreateSkybox:
                split.prop(settings,"sceneSkyBoxCubeTexture",text="Texture")
                split=split.split()
                split.prop(settings,"sceneSkyBoxHDR",text="HDR")
                

        box = layout.box()
        row = box.row()
        row.prop(settings,"runtimeShowPhysics",text="show physics")
        if settings.runtimeShowPhysics:
            row.prop(settings,"runtimeShowPhysicsDepth",text="use depth test")

class URHO_PT_mainuserdata(bpy.types.Panel):
    bl_idname = "URHO_PT_MAINCOMPONENT"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Urho3D"
    bl_label ="Urho3D-Components"

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        obj = bpy.context.active_object
        layout = self.layout
        ObjectComponentSubpanel(obj,layout)

class URHO_PT_mainobject(bpy.types.Panel):
    bl_idname = "URHO_PT_MAINOBJECT"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Urho3D"
    bl_label ="Urho3D-Object"

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        obj = bpy.context.active_object

        if not obj:
            return

        layout = self.layout
        if obj.type=="MESH":
            row = layout.row()
            row.prop(obj,"hide_render",text="Invisibile", toggle=False)
            row = layout.row()
            row.label(text="Shadow Settings")
            row = layout.row()
            row.prop(obj,"cast_shadow")

class URHO_PT_mainmesh(bpy.types.Panel):
    bl_idname = "URHO_PT_MAINMESH"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Urho3D"
    bl_label ="Urho3D-Mesh"

    @classmethod
    def poll(cls, context):
        obj = bpy.context.active_object
        return obj and obj.type=="MESH"

    def draw(self, context):
        MeshUI(self,context)



class URHO_PT_maincomponent(bpy.types.Panel):
    bl_idname = "URHO_PT_MAINUSERDATA"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Urho3D"
    bl_label ="Urho3D-Userdata"

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        obj = bpy.context.active_object
        if obj:

            box = layout.box()
            row = box.row()
            row.label(text="Object-Name:")
            row = box.row()
            row.prop(obj,"name",text="")
            ObjectUserData(obj,layout)
        


class URHO_PT_mainmaterial(bpy.types.Panel):
    bl_idname = "URHO_PT_MAINMATERIAL"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Urho3D"
    bl_label ="Urho3D-Material"

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type=="MESH"

    def draw(self, context):
        settings = bpy.context.scene.urho_exportsettings

        layout = self.layout

        obj = bpy.context.active_object

        ObjectMaterialNodetree(obj,layout)

#--------------------
# Handlers
#--------------------
def get_default_context():
    window = bpy.context.window_manager.windows[0]
    return {'window': window, 'screen': window.screen}
    
# Called after loading a new blend. Set the default path if the path edit box is empty.        
@persistent
def PostLoad(dummy):
    addonPrefs = bpy.context.preferences.addons[__name__].preferences
    settings = bpy.context.scene.urho_exportsettings
    settings.errorsMem.Clear()
    settings.updatingProperties = False
    settings.reset_paths(bpy.context, False)
    setup_json_nodetree()
    ctx=bpy.context
    PublishRuntimeSettings(settings,bpy.context)

def has_non_objectmode_parent(obj):
    current_parent=obj.parent
    while current_parent:
        try:
            if current_parent.mode!="OBJECT":
                return True
        except:
            return True # no mode, no relevant object => no object mode
        current_parent = current_parent.parent
    return False

@persistent
def on_depsgraph_update_post(self):
    # Recache
    depsgraph = bpy.context.evaluated_depsgraph_get()

    if len(depsgraph.updates)>0:
        for update in depsgraph.updates:
            try:
                if update.is_updated_transform and hasattr(update.id,"type"):
                    obj = update.id

                    if obj.type!="ARMATURE" and obj.animation_data:
                        # object with object animation, don't save, otherwise transform would be reset according to the current animation
                        continue

                    if obj.mode!="OBJECT" or has_non_objectmode_parent(obj):
                        continue
                    
                    UpdateCheck.pos = obj.location
                    UpdateCheck.rot = obj.rotation_euler
                    UpdateCheck.scale = obj.scale
                    UpdateCheck.modified_obj = obj
                    print("Updated:%s" % update.id.name)

                    UpdateCheck.request_save_scene = True
                    return
            except:
                pass

@persistent
def PostSave(dummy):
    settings = bpy.context.scene.urho_exportsettings
    if settings.exportOnSave:

        if settings.exportOnSaveMode=='ALL':
            bpy.ops.urho.export(ignore_geo_skel_anim=False)
        elif settings.exportOnSaveMode=='NOGEO':
            print("NOGEO")
            bpy.ops.urho.export(ignore_geo_skel_anim=True)
        elif settings.exportOnSaveMode=="MAT":
            bpy.ops.urho.exportmaterials()
        else:
            print("UNKNOWN SAVEMODE %s" % settings.exportOnSaveMode)

        print("AUTO EXPORT on SAVE")
        
    


#--------------------
# Register Unregister
#--------------------

# Called when the addon is enabled. Here we register out UI classes so they can be 
# used by Python scripts.

addon_keymaps = []

ntSelectedObject = None

tick = 0.05

zone_cubemap=[("None","None","None",0)]

def callback_after_nodetreecreation():
    global zone_cubemap
    try:
        zone_cubemap=[("None","None","None",0)] + JSONNodetree.globalData["cubeTextures_elemitems"]
    except:
        zone_cubemap=[("None","None","None",0)]                

JSONNodetreeUtils.AfterNodeTreeCreationCallback=callback_after_nodetreecreation

class UpdateCheck:
    last_pos = None
    last_rot = None
    last_scale = None
    last_obj = None

    request_save_scene = False
    pos=None
    rot=None
    scale=None
    modified_obj=None  
    timer = 1.0 

    saving = False 

# timer callback
#if 'call_execution_queue' not in globals():
def call_execution_queue():
    # flush the actions
    execution_queue.flush_actions()
    # come back in 0.1s

    #print("ping_check:%s" % PingData.ping_check_running)

    if bpy.context.scene.render.engine=="URHO3D":
        if PingData.ping_auto_timer<=0:
            execution_queue.execute_or_queue_action(PingForRuntime) 
        else:
            PingData.ping_auto_timer -= tick
            #print("PingData.auto_timer %s" % PingData.ping_auto_timer)

        settings = bpy.context.scene.urho_exportsettings
        if UpdateCheck.request_save_scene and settings.outputPath:
            UpdateCheck.timer-=tick
            #print("Check[%s]: %s=%s %s=%s %s=%s " %(UpdateCheck.timer,UpdateCheck.last_pos,UpdateCheck.pos,UpdateCheck.last_rot,UpdateCheck.rot,UpdateCheck.last_scale,UpdateCheck.scale))
 

            isTransSame = UpdateCheck.last_pos==UpdateCheck.pos and UpdateCheck.last_rot==UpdateCheck.rot and UpdateCheck.last_scale==UpdateCheck.scale

            if not UpdateCheck.saving and isTransSame and UpdateCheck.timer<=0:
                print("EXPORT EXPORT")
                #ExecuteAddon(bpy.context,True,True)
                if settings.runtimeAutoUpdateTransforms:
                    bpy.ops.urho.exportcommand()
                    #bpy.ops.urho.export(ignore_geo_skel_anim=True)
                UpdateCheck.modified_obj=None
                UpdateCheck.last_obj=None
                UpdateCheck.last_pos=None
                UpdateCheck.last_rot=None
                UpdateCheck.last_scale=None
                UpdateCheck.pos=None
                UpdateCheck.rot=None
                UpdateCheck.scale=None
                UpdateCheck.request_save_scene=False
                UpdateCheck.timer=1.0
            else:
                UpdateCheck.last_obj=UpdateCheck.modified_obj
                UpdateCheck.last_pos=UpdateCheck.pos
                UpdateCheck.last_rot=UpdateCheck.rot
                UpdateCheck.last_scale=UpdateCheck.scale


        

    if PingData.ping_check_running:
        bpy.context.scene.view_settings.view_transform = 'Raw'

        if PingData.ping_runtime_timer <= 0:
            PingData.ping_runtime_timer = PingData.ping_runtime_interval

            _data = {}
            _data["session_id"]=GetSessionId()
            setJson = json.dumps(_data, indent=4)
            data = str.encode(setJson)
            Publish("blender","ping","json",data)
            PingData.ping_count += 1
        else:
            PingData.ping_runtime_timer -= tick

        if PingData.ping_count > 2 and not found_blender_runtime():
            print("auto start runtime")
            try:
                bpy.ops.urho.start_runtime()
            except:
                pass
            set_found_blender_runtime(True)
            PingData.ping_check_running = True
    

    return tick
        
def customAutoSelection(current_obj,current_treetype,current_tree):
    global ntSelectedObject
    def chooseRighTreeForObject(current_obj,current_treetype,current_tree):
        global ntSelectedObject

        if current_treetype=="urho3dcomponents" and current_obj:
            selectNT = current_obj.list_index_nodetrees
            if current_obj and len(current_obj.nodetrees)>0 and current_obj.nodetrees[selectNT].nodetreePointer:
                try:
                    autoNodetree = current_obj.nodetrees[selectNT].nodetreePointer
                    ntSelectedObject = current_obj                                
                    return autoNodetree
                except:
                    pass
        elif current_treetype=="urho3dmaterials" and current_obj.type=="MESH" and len(current_obj.data.materialNodetrees)>0:
            if current_obj and current_obj.data and len(current_obj.data.materialNodetrees)>0:
                selectNT = current_obj.data.list_index_nodetrees
                try:
                    slot = current_obj.data.materialNodetrees[bpy.context.object.active_material_index]                                  
                    if slot.nodetreePointer:
                        autoNodetree = slot.nodetreePointer
                    ntSelectedObject = current_obj
                    return autoNodetree
                except:
                    return "NOTREE"
    # aprint("CUSTOM CHECK:%s %s %s" % (current_obj.name,current_treetype,current_tree))
    # check if we have at least one nodetree for this object
    if bpy.data.worlds[0].jsonNodes.autoSelectObjectNodetree:
        return chooseRighTreeForObject(current_obj,current_treetype,current_tree)     
        # dont show anything if in auto mode and no nodetree found
    else:
        # when a different treetype is chosen than seen, change this. once
        if (current_treetype and current_tree and current_treetype!=current_tree.bl_idname):
            return chooseRighTreeForObject(current_obj,current_treetype,current_tree)     

    return None


def setup_json_nodetree():
    # setup json-nodetree
    JSONNodetreeUtils.overrideAutoNodetree = customAutoSelection
    bpy.data.worlds[0].jsonNodes.path_ui_name = "Material-JSON"
    bpy.data.worlds[0].jsonNodes.path2_ui_name = "Component-JSON"
    bpy.data.worlds[0].jsonNodes.load_trees_button_name = "Load Trees"
    bpy.data.worlds[0].jsonNodes.show_custom_ui_field = False
    bpy.data.worlds[0].jsonNodes.show_developer = False
    bpy.data.worlds[0].jsonNodes.show_export_panel = False
    bpy.data.worlds[0].jsonNodes.show_auto_select = False
    bpy.data.worlds[0].jsonNodes.show_object_mapping = False
    print("--ok--")


def register():
    try:
        jsonnodetree_register()
        bpy.utils.register_class(URHO3D_JSONNODETREE_REBRAND)
        #bpy.unregister_class(NODE_PT_json_nodetree_file)
    except:
        desired_trace = traceback.format_exc()
        print("Unexpected error in jsonnodetree_register:", desired_trace)

    try:    
        addon_blender_connect_register()
    except:
        print("Unexpected error in addon_blender_connect_register:", sys.exc_info()[0])

    
    def OnRuntimeMessage(topic,subtype,meta,data):

        def QueuedExecution():
            #print("init onRuntime %s - %s - %s - %s" % ( topic,subtype,meta,data ))
            if topic == "runtime" and subtype == "hello":
                settings = bpy.context.scene.urho_exportsettings
                PublishRuntimeSettings(settings,bpy.context)
                bpy.ops.urho.exportmaterials()

        execution_queue.execute_or_queue_action(QueuedExecution)  

    AddListener("runtime",OnRuntimeMessage)     


        # property hooks:
    def updateMaterialTreeName(self,ctx):
        if self.materialTreeId!=-1:
            ctx.space_data.node_tree = JSONNodetreeUtils.getNodetreeById(self.materialTreeId)
        else:
            ctx.space_data.node_tree = None

    def getMaterialTreeName(self):
        # print("get")
        if self.materialTreeId == -1:
            #print("No nodetree(%s)" % self.name)
            return ""
        
        nodetree = JSONNodetreeUtils.getNodetreeById(self.materialTreeId)
        if nodetree:
            return nodetree.name
        else:
            return ""

    def setMaterialTreeName(self,value):
        if value == "":
            #print("RESETID")
            self.materialTreeId = -1
        else:
            #print("set %s=%s" % (self.name, str(value) ))
            nodetree = bpy.data.node_groups[value]
            self.materialTreeId = JSONNodetreeUtils.getID(nodetree)
            #print("assigned ID %s" % getID(nodetree))


    ## SCENE-Node-Tree

        # property hooks:
    def updateSceneTreeName(self,ctx):
        if self.sceneTreeId!=-1:
            ctx.space_data.node_tree = JSONNodetreeUtils.getNodetreeById(self.sceneTreeId)
        else:
            ctx.space_data.node_tree = None

    def getSceneTreeName(self):
        # print("get")
        if self.sceneTreeId == -1:
            #print("No nodetree(%s)" % self.name)
            return ""
        
        nodetree = JSONNodetreeUtils.getNodetreeById(self.sceneTreeId)
        if nodetree:
            return nodetree.name
        else:
            return ""

    def setSceneTreeName(self,value):
        if value == "":
            #print("RESETID")
            self.sceneTreeId = -1
        else:
            #print("set %s=%s" % (self.name, str(value) ))
            nodetree = bpy.data.node_groups[value]
            self.sceneTreeId = JSONNodetreeUtils.getID(nodetree)
            #print("assigned ID %s" % getID(nodetree))            
            

    if DEBUG: print("Urho export register")
    
    #bpy.utils.register_module(__name__)
    
    try:
        bpy.utils.register_class(UrhoRenderEngine)
    except:
        print("Unexpected error in jsonnodetree_register_ui:%s" % traceback.format_exc())

    reRegister()
    bpy.utils.register_class(UrhoAddonPreferences)
    bpy.utils.register_class(UrhoExportSettings)
    bpy.utils.register_class(UrhoExportGlobalSettings)
    bpy.utils.register_class(UrhoExportMeshSettings)
    bpy.utils.register_class(UrhoExportOperator)
    bpy.utils.register_class(UrhoExportSelectLodMesh)
    bpy.utils.register_class(UrhoExportMaterialsOnlyOperator)
    bpy.utils.register_class(UrhoExportCommandOperator)
    bpy.utils.register_class(UrhoExportResetOperator)
    bpy.utils.register_class(UrhoExportResetPathsOperator)
    bpy.utils.register_class(UrhoExportRenderPanel)
    bpy.utils.register_class(UrhoExportObjectPanel)
    bpy.utils.register_class(UrhoExportMaterialPanel)
    bpy.utils.register_class(UrhoExportStartRuntime)
    bpy.utils.register_class(UrhoExportStartRuntime2)
    bpy.utils.register_class(UrhoApplyVertexData)
    bpy.utils.register_class(ApplyExportUrhoToCollectionChildren)
    bpy.utils.register_class(UL_URHO_NODETREE_SET_NODETREE_TO_SELECTED)
    bpy.utils.register_class(URHO_PT_mainscene)
    bpy.utils.register_class(URHO_PT_maincomponent)
    bpy.utils.register_class(URHO_PT_mainmaterial)
    bpy.utils.register_class(URHO_PT_mainuserdata)
    bpy.utils.register_class(PackOutputFolder)
    bpy.utils.register_class(UrhoCreateNodetreeFromMaterial)
    bpy.utils.register_class(URHO_PT_mainobject)
    bpy.utils.register_class(URHO_PT_mainmesh)
    

    
    bpy.utils.register_class(UrhoReportDialog)
    bpy.utils.register_class(KeyValue)
    
    bpy.utils.register_class(UL_URHO_LIST_USERDATA)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_USERDATA)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_DEL_USERDATA)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_MOVE_USERDATA)
    
    
    bpy.utils.register_class(UL_URHO_LIST_CREATE_GENERIC)

    bpy.types.Scene.urho_exportsettings = bpy.props.PointerProperty(type=UrhoExportSettings)
    bpy.types.Scene.nodetree = bpy.props.PointerProperty(type=bpy.types.NodeTree,poll=poll_component_nodetree);
    bpy.types.NodeTree.initialized = bpy.props.BoolProperty(default=False)

    bpy.types.Object.user_data = bpy.props.CollectionProperty(type=KeyValue)
    bpy.types.Object.list_index_userdata = IntProperty(name = "Index for key value list",default = 0)
    bpy.types.Object.cast_shadow = bpy.props.BoolProperty(default=True)
    bpy.types.Object.receive_shadow = bpy.props.BoolProperty(default=True)
    
    bpy.types.Light.use_pbr=bpy.props.BoolProperty()
    bpy.types.Light.brightness_mul=bpy.props.FloatProperty(min=0.0,max=90000.0,default=1.0)

    bpy.types.Mesh.ID = bpy.props.IntProperty(default=-1)
    bpy.types.Mesh.urho_export = bpy.props.PointerProperty(type=UrhoExportMeshSettings)

    #bpy.types.Mesh.IDNAME=bpy.props.StringProperty(get=getMeshName,set=setMeshName,update=updateMeshName)

    # lod
    bpy.utils.register_class(LODData)
    bpy.utils.register_class(LODSet)

    bpy.types.Object.ID = bpy.props.IntProperty(default=-1)
    bpy.types.Object.lodsetID = bpy.props.IntProperty()
    bpy.types.Object.lodsetName = bpy.props.StringProperty(get=getLodSetName,set=setLodSetName,update=updateLodSetName)
    bpy.types.World.lodsets=bpy.props.CollectionProperty(type=LODSet)
    bpy.types.World.lodset_counter=bpy.props.IntProperty()
    bpy.types.World.meshid_counter=bpy.props.IntProperty()
    bpy.types.World.global_settings=bpy.props.PointerProperty(type=UrhoExportGlobalSettings)
    bpy.types.World.objid_counter=bpy.props.IntProperty()
    bpy.types.Collection.urhoExport = bpy.props.BoolProperty(description="export as urho3d object")

    
    
    bpy.utils.register_class(UL_URHO_LIST_LOD)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_LOD)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_DEL_LOD)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_MOVE_LOD)    
    bpy.utils.register_class(UrhoExportMeshPanel)

    bpy.utils.register_class(UrhoExportNodetreePanel)
    bpy.utils.register_class(UrhoExportScenePanel)

    bpy.utils.register_class(UL_URHO_LIST_NODETREE)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_NODETREE)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_DEL_NODETREE)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_MOVE_NODETREE)
    bpy.utils.register_class(NodetreeInfo)
    bpy.types.Object.nodetrees = bpy.props.CollectionProperty(type=NodetreeInfo)
    bpy.types.Object.list_index_nodetrees = IntProperty(name = "Index for nodetree list",default = 0)


    bpy.utils.register_class(UL_URHO_LIST_MATERIAL_NODETREE)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_MATERIAL_NODETREE)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_DEL_MATERIAL_NODETREE)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_MOVE_MATERIAL_NODETREE)
    bpy.utils.register_class(MaterialNodetreeInfo)
    bpy.types.Mesh.materialNodetrees = bpy.props.CollectionProperty(type=MaterialNodetreeInfo)
    bpy.types.Mesh.list_index_nodetrees = IntProperty(name = "Index for nodetree list",default = 0)

    #bpy.types.Mesh.materialNodetree=bpy.props.PointerProperty(type=bpy.types.NodeTree,poll=poll_material_nodetree)


        





    
    #unregisterSelectorPanel()
    #bpy.utils.unregister_class(NODE_PT_json_nodetree_select)
    
    print("ok!")

    print("activate autoload-timers")
    #bpy.context.preferences.filepaths.use_relative_paths = False
    
    if not PostLoad in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(PostLoad)

    if not PostSave in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(PostSave)

    if not on_depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update_post)

    bpy.app.timers.register(call_execution_queue,persistent=True)        



    execution_queue.queue_action(setup_json_nodetree)

    execution_queue.queue_action(jsonnodetree_activateTimers)


    # handle the shortcuts
    wm = bpy.context.window_manager
    
    #km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    km = wm.keyconfigs.addon.keymaps.new('Window', space_type='EMPTY', region_type='WINDOW', modal=False)

    kmi = km.keymap_items.new("urho.start_runtime", 'A', 'PRESS', ctrl=True,shift=True)
    kmi = km.keymap_items.new("urho.start_runtime2", 'Q', 'PRESS', ctrl=True,shift=True)
    addon_keymaps.append(km)

    print("installed addons: %s" % bpy.context.preferences.addons.keys())

# Note: the script __init__.py is executed only the first time the addons is enabled. After that
# disabling or enabling the script will only call unregister() or register(). So in unregister()
# delete only objects created with register(), do not delete global objects as they will not be
# created re-enabling the addon.
# __init__.py is re-executed pressing F8 or randomly(?) enabling the addon.



# Called when the addon is disabled. Here we remove our UI classes.
def unregister():
    try:
        jsonnodetree_unregister()
        bpy.utils.unregister_class(URHO3D_JSONNODETREE_REBRAND)
    except:
        print("Unexpected error in jsonnodetree_register:", sys.exc_info()[0])

    try:
        addon_blender_connect_unregister()
    except:
        print("Unexpected error in addon_blender_connect_unregister:", sys.exc_info()[0])        
    
    if DEBUG: print("Urho export unregister")
    
    #bpy.utils.unregister_module(__name__)

    reUnregister()
    bpy.utils.unregister_class(UrhoRenderEngine)
    bpy.utils.unregister_class(UrhoAddonPreferences)
    bpy.utils.unregister_class(UrhoExportSettings)
    bpy.utils.unregister_class(UrhoExportSelectLodMesh)
    bpy.utils.unregister_class(UrhoExportOperator)
    bpy.utils.unregister_class(UrhoExportMaterialsOnlyOperator)
    bpy.utils.unregister_class(UrhoExportCommandOperator)
    bpy.utils.unregister_class(UrhoExportResetOperator)
    bpy.utils.unregister_class(UrhoExportResetPathsOperator)  
    bpy.utils.unregister_class(UrhoExportStartRuntime)  
    bpy.utils.unregister_class(UrhoExportMeshSettings)
    bpy.utils.unregister_class(UrhoApplyVertexData)
    bpy.utils.unregister_class(UrhoExportMaterialPanel)
    bpy.utils.unregister_class(UrhoExportGlobalSettings)
    bpy.utils.unregister_class(UrhoExportStartRuntime2)
    bpy.utils.unregister_class(ApplyExportUrhoToCollectionChildren)
    bpy.utils.unregister_class(UL_URHO_NODETREE_SET_NODETREE_TO_SELECTED)
    bpy.utils.unregister_class(URHO_PT_mainscene) 
    bpy.utils.unregister_class(URHO_PT_mainuserdata)    
    bpy.utils.unregister_class(URHO_PT_mainmaterial)
    bpy.utils.unregister_class(URHO_PT_maincomponent)
    bpy.utils.unregister_class(PackOutputFolder)
    bpy.utils.unregister_class(UrhoCreateNodetreeFromMaterial)
    bpy.utils.unregister_class(URHO_PT_mainobject)
    bpy.utils.unregister_class(URHO_PT_mainmesh)



    try:
        bpy.utils.unregister_class(UrhoExportRenderPanel)
    except:
        pass
    try:
        bpy.utils.unregister_class(UrhoExportObjectPanel)
    except:
        pass

    bpy.utils.unregister_class(UL_URHO_LIST_CREATE_GENERIC)
    bpy.utils.unregister_class(UrhoReportDialog)
    bpy.utils.unregister_class(KeyValue)
    bpy.utils.unregister_class(UL_URHO_LIST_USERDATA)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_USERDATA)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_DEL_USERDATA)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_MOVE_USERDATA)
    

    bpy.utils.unregister_class(LODData)
    bpy.utils.unregister_class(LODSet)
    bpy.utils.unregister_class(UL_URHO_LIST_LOD)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_LOD)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_DEL_LOD)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_MOVE_LOD)
    bpy.utils.unregister_class(UrhoExportMeshPanel)

    
    del bpy.types.Scene.urho_exportsettings
    del bpy.types.Object.user_data
    del bpy.types.NodeTree.initialized
    
    bpy.utils.unregister_class(UL_URHO_LIST_NODETREE)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_NODETREE)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_DEL_NODETREE)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_MOVE_NODETREE)

    bpy.utils.unregister_class(UL_URHO_LIST_MATERIAL_NODETREE)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_MATERIAL_NODETREE)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_DEL_MATERIAL_NODETREE)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_MOVE_MATERIAL_NODETREE)
    bpy.utils.unregister_class(MaterialNodetreeInfo)
    del bpy.types.Mesh.materialNodetrees
    del bpy.types.Mesh.list_index_nodetrees

    bpy.utils.unregister_class(NodetreeInfo)
    del bpy.types.Object.nodetrees
    del bpy.types.Object.list_index_nodetrees

    bpy.utils.unregister_class(UrhoExportNodetreePanel)
    bpy.utils.unregister_class(UrhoExportScenePanel)

    del bpy.types.Scene.nodetree
#    del bpy.types.Scene.sceneTreeId
    del bpy.types.Collection.urhoExport


    bpy.app.timers.unregister(call_execution_queue)        

    if PostLoad in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(PostLoad)
    if PostSave in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(PostSave)

    #unregister keyboard shortcuts
    wm = bpy.context.window_manager
    for km in addon_keymaps:
        wm.keyconfigs.addon.keymaps.remove(km)
    # clear the list
    addon_keymaps.clear()

#--------------------
# Blender UI utility
#--------------------


# Select vertices on a object
def selectVertices(context, objectName, indicesList, deselect):

    objects = context.scene.objects
    
    try:
        obj = objects[objectName]
    except KeyError:
        log.error( "Cannot select vertices on not found object {:s}".format(objectName) )
        return

    # Set the object as current
    #objects.active = obj
    context.view_layer.objects.active=obj
    # Enter Edit mode (check poll() to avoid exception)
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    # Deselect all
    if deselect and bpy.ops.mesh.select_all.poll():
        bpy.ops.mesh.select_all(action='DESELECT')
    # Save the current select mode
    sel_mode = bpy.context.tool_settings.mesh_select_mode
    # Set Vertex select mode
    bpy.context.tool_settings.mesh_select_mode = [True, False, False]
    # Exit Edit mode
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    # Select the vertices
    mesh = obj.data
    for index in indicesList:
        try:
            mesh.vertices[index].select = True
        #except KeyError:
        except IndexError:
            pass
    # Back in Edit mode
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    # Restore old selection mode
    bpy.context.tool_settings.mesh_select_mode = sel_mode 

from collections import defaultdict

# Select vertices with errors
def selectErrors(context, errorsMem, errorName):
    names = errorsMem.Names()
    if errorName != 'ALL':
        names = [errorName]
    for i, name in enumerate(names):
        errors = errorsMem.Get(name)
        if not errors:
            continue
        indices = defaultdict(set)
        for mi, vi in errors:
            objectName = errorsMem.Second(mi)
            if objectName:
                indices[objectName].add(vi)
        for objectName, indicesSet in indices.items():
            count = len(indicesSet)
            if count:
                log.info( "Selecting {:d} vertices on {:s} with '{:s}' errors".format(count, objectName, name) )
                selectVertices(context, objectName, indicesSet, i == 0)

#-------------------------------------------------------------------------
# Export materials only
#-------------------------------------------------------------------------
def ExecuteUrhoExportMaterialsOnly(context):
    global logList

    # Check Blender version
    if bpy.app.version < (2, 80, 0):
        log.error( "Blender version 2.70 or later is required" )
        return False

    # Clear log list
    logList[:] = []
    
    # Get exporter UI settings
    settings = context.scene.urho_exportsettings

    # File utils options
    fOptions = FOptions()

    fOptions.useSubDirs = settings.useSubDirs
    fOptions.fileOverwrite = settings.fileOverwrite
    fOptions.paths[PathType.ROOT] = settings.outputPath
    fOptions.paths[PathType.MODELS] = settings.modelsPath
    fOptions.paths[PathType.ANIMATIONS] = settings.animationsPath
    fOptions.paths[PathType.TRIGGERS] = settings.animationsPath
    fOptions.paths[PathType.MATERIALS] = settings.materialsPath
    fOptions.paths[PathType.TECHNIQUES] = settings.techniquesPath
    fOptions.paths[PathType.TEXTURES] = settings.texturesPath
    fOptions.paths[PathType.MATLIST] = settings.modelsPath
    fOptions.paths[PathType.OBJECTS] = settings.objectsPath
    fOptions.paths[PathType.SCENES] = settings.scenesPath

    UrhoWriteMaterialTrees(fOptions,True)


#-------------------------------------------------------------------------
# Export main
#-------------------------------------------------------------------------


def ExecuteUrhoExport(context):
    global logList

    # Check Blender version
    if bpy.app.version < (2, 80, 0):
        log.error( "Blender version 2.70 or later is required" )
        return False

    # Clear log list
    logList[:] = []
    
    # Get exporter UI settings
    settings = context.scene.urho_exportsettings

    # File utils options
    fOptions = FOptions()

    # List where to store tData (decomposed objects)
    tDataList = []
    # Decompose options
    tOptions = TOptions()

    # Scene export data
    uScene = UrhoScene(context.scene)
    # Scene export options
    sOptions = SOptions()
    
    # Addons preferences
    addonPrefs = context.preferences.addons[__name__].preferences
    
    # Copy from exporter UI settings to Decompose options
    tOptions.mergeObjects = settings.merge
    tOptions.mergeNotMaterials = settings.mergeNotMaterials
    tOptions.doForceElements = settings.forceElements
    tOptions.useLods = settings.lods
    tOptions.onlySelected = (settings.source == 'ONLY_SELECTED')
    tOptions.ignoreHidden = settings.ignoreHidden
    tOptions.scale = settings.scale
    tOptions.globalOrigin = (settings.origin == 'GLOBAL')
    tOptions.applyModifiers = settings.modifiers
    tOptions.applySettings = settings.modifiersRes
    tOptions.doBones = settings.skeletons
    tOptions.doOnlyKeyedBones = settings.onlyKeyedBones
    tOptions.doOnlyDeformBones = settings.onlyDeformBones
    tOptions.doOnlyVisibleBones = settings.onlyVisibleBones
    tOptions.actionsByFcurves = settings.actionsByFcurves
    tOptions.skinBoneParent = settings.parentBoneSkinning
    tOptions.derigifyArmature = settings.derigify
    tOptions.doAnimations = settings.animations
    tOptions.doObjAnimations = settings.objAnimations
    tOptions.doAllActions = (settings.animationSource == 'ALL_ACTIONS')
    tOptions.doCurrentAction = (settings.animationSource == 'CURRENT_ACTION')
    tOptions.doUsedActions = (settings.animationSource == 'USED_ACTIONS')
    tOptions.doSelectedActions = (settings.animationSource == 'SELECTED_ACTIONS')
    tOptions.doSelectedStrips = (settings.animationSource == 'SELECTED_STRIPS')
    tOptions.doSelectedTracks = (settings.animationSource == 'SELECTED_TRACKS')
    tOptions.doStrips = (settings.animationSource == 'ALL_STRIPS')
    tOptions.doTracks = (settings.animationSource == 'ALL_TRACKS')
    tOptions.doTimeline = (settings.animationSource == 'TIMELINE')
    tOptions.doTriggers = settings.animationTriggers
    tOptions.doAnimationExtraFrame = settings.animationExtraFrame
    tOptions.doAnimationPos = settings.animationPos
    tOptions.doAnimationRot = settings.animationRot
    tOptions.doAnimationSca = settings.animationSca
    tOptions.filterSingleKeyFrames = settings.filterSingleKeyFrames
    tOptions.doGeometries = settings.geometries
    tOptions.doGeometryPos = settings.geometryPos
    tOptions.doGeometryNor = settings.geometryNor
    tOptions.doGeometryCol = settings.geometryCol
    tOptions.doGeometryColAlpha = settings.geometryColAlpha
    tOptions.doGeometryUV  = settings.geometryUV
    tOptions.doGeometryUV2  = settings.geometryUV2
    tOptions.doGeometryTan = settings.geometryTan
    tOptions.doGeometryWei = settings.geometryWei
    tOptions.doMorphs = settings.morphs
    tOptions.doMorphNor = settings.morphNor
    tOptions.doMorphTan = settings.morphTan
    tOptions.doMorphUV = settings.morphTan
    tOptions.doOptimizeIndices = settings.optimizeIndices
    tOptions.doMaterials = settings.materials or settings.textures
    tOptions.bonesGlobalOrigin = settings.bonesGlobalOrigin
    tOptions.actionsGlobalOrigin = settings.actionsGlobalOrigin

    tOptions.orientation = None # ='Y_PLUS'
    if settings.orientation == 'X_PLUS':
        tOptions.orientation = Quaternion((0.0,0.0,1.0), radians(90.0))
    elif settings.orientation == 'X_MINUS':
        tOptions.orientation = Quaternion((0.0,0.0,1.0), radians(-90.0))
    elif settings.orientation == 'Y_MINUS':
        tOptions.orientation = Quaternion((0.0,0.0,1.0), radians(180.0))
    elif settings.orientation == 'Z_PLUS':
        tOptions.orientation = Quaternion((1.0,0.0,0.0), radians(-90.0)) * Quaternion((0.0,0.0,1.0), radians(180.0))
    elif settings.orientation == 'Z_MINUS':
        tOptions.orientation = Quaternion((1.0,0.0,0.0), radians(90.0)) * Quaternion((0.0,0.0,1.0), radians(180.0))

    sOptions.shapeItems = settings.shapeItems
    for shapeItems in settings.shapeItems:
        if shapeItems[0] == settings.shape:
            tOptions.shape = shapeItems[1]
            sOptions.shape = shapeItems[1]
            break
    tOptions.meshNameDerivedBy = settings.meshnameDerivedBy

    sOptions.mergeObjects = settings.merge
    sOptions.doIndividualPrefab = settings.individualPrefab
    sOptions.individualPrefab_onlyRootObject = settings.individualPrefab_onlyRootObject
    sOptions.doCollectivePrefab = settings.collectivePrefab
    sOptions.doScenePrefab = settings.scenePrefab
    sOptions.SceneCreateZone = settings.sceneCreateZone
    sOptions.ZoneTexture = settings.sceneZoneCubeTexture
    sOptions.sceneCreateSkybox = settings.sceneCreateSkybox
    sOptions.sceneSkyBoxCubeTexture = settings.sceneSkyBoxCubeTexture
    sOptions.noPhysics = (settings.physics == 'DISABLE')
    sOptions.individualPhysics = (settings.physics == 'INDIVIDUAL')
    sOptions.wiredAsEmpty = settings.wiredAsEmpty
    sOptions.exportGroupsAsObject = settings.exportGroupsAsObject
    sOptions.exportObjectCollectionAsTag = settings.exportObjectCollectionAsTag
    sOptions.globalPhysics = (settings.physics == 'GLOBAL')
    sOptions.trasfObjects = settings.trasfObjects
    sOptions.exportUserdata = settings.export_userdata
    sOptions.globalOrigin = tOptions.globalOrigin
    sOptions.orientation = tOptions.orientation
    sOptions.objectsPath = settings.objectsPath

    fOptions.useSubDirs = settings.useSubDirs
    fOptions.fileOverwrite = settings.fileOverwrite
    fOptions.paths[PathType.ROOT] = settings.outputPath
    fOptions.paths[PathType.MODELS] = settings.modelsPath
    fOptions.paths[PathType.ANIMATIONS] = settings.animationsPath
    fOptions.paths[PathType.TRIGGERS] = settings.animationsPath
    fOptions.paths[PathType.MATERIALS] = settings.materialsPath
    fOptions.paths[PathType.TECHNIQUES] = settings.techniquesPath
    fOptions.paths[PathType.TEXTURES] = settings.texturesPath
    fOptions.paths[PathType.MATLIST] = settings.modelsPath
    fOptions.paths[PathType.OBJECTS] = settings.objectsPath
    fOptions.paths[PathType.SCENES] = settings.scenesPath

    settings.errorsMem.Clear()


    if settings.onlyErrors:
        log.setLevel(logging.WARNING)
    else:
        log.setLevel(logging.DEBUG)

    if not settings.outputPath:
        log.error( "Output path is not set" )
        return False

    if tOptions.mergeObjects and not tOptions.globalOrigin:
        log.warning("To merge objects you should use Origin = Global")

    # create dummy objects to each lodset
    print("LODSETS:\n");
    for lodset in bpy.data.worlds[0].lodsets:
        firstLOD = True
        for lod in lodset.lods:
            if not lod.meshObj:
                print("NO MESH for %s lod-distance:%s" % (lodset.name,lod.distance) );
                continue
            new_objname = "%s_LOD%s" % (lodset.name,str(lod.distance).zfill(3))
            lodmesh = lod.meshObj
            #new_obj = bpy.data.objects.new(name=new_objname,object_data=lodmesh)
            new_obj = None
            if lodset.armatureObj and lodset.armatureObj.name!="":
                ## todo: make sure this is mesh and make sure to really duplicate everything...!? (sense?)
                armaObj = lodset.armatureObj
                firstChild = armaObj.children[0]
                
                new_obj = firstChild.copy()
                new_obj.name = new_objname 
                new_obj.data = lodmesh
                new_obj.animation_data_clear()
                new_obj.parent = None
                new_obj.location = armaObj.location
                # TODO: Check if you this assuption is true. (Quaternion or else Euler)
                if armaObj.rotation_mode=="QUATERNION":
                    new_obj.rotation_quaternion = armaObj.rotation_quaternion
                else:
                    new_obj.rotation_euler = armaObj.rotation_euler
                new_obj.scale = armaObj.scale                

                #scn.objects.link(new_obj)
            if not new_obj:
                new_obj = bpy.data.objects.new(name=new_objname,object_data=lodmesh)

            ## mark this object to be temporary lodset object (used to assure applyModifier)
            new_obj.lodsetID=-2
            # check if this lodset has an armature set
            if lodset.armatureObj and firstLOD:
                # create an armature-modifier for the lod-export to export this arma as well
                arma_mod = new_obj.modifiers.new(name="__lod_armature", type="ARMATURE")
                
                # set the arma
                arma_mod.object=lodset.armatureObj
            
            # add decimate-modifier if the decimate was < 1.0
            
            if not lodset.armatureObj:
                decimate = new_obj.modifiers.new(name="__decimate",type="DECIMATE")
                decimate.ratio = lod.decimate

            firstLOD = False
            tempObjects.append(new_obj)
            bpy.context.scene.collection.objects.link(new_obj)
            print ("LODSET:%s" % lodset.name)

    # Decompose
    if DEBUG: ttt = time.time() #!TIME
    Scan(context, tDataList, settings.errorsMem, tOptions)
    if DEBUG: print("[TIME] Decompose in {:.4f} sec".format(time.time() - ttt) ) #!TIME

    # keep track of all meshes that we processed and avoid multiple handling
    processedMeshes = []

    # Export each decomposed object
    for tData in tDataList:
    
        #PrintAll(tData)
        
        log.info("---- Exporting {:s} ----".format(tData.objectName))

        uExportData = UrhoExportData()
        
        uExportOptions = UrhoExportOptions()
        uExportOptions.splitSubMeshes = settings.geometrySplit
        uExportOptions.useStrictLods = settings.strictLods
        uExportOptions.useRatioTriggers = settings.animationRatioTriggers
        uExportOptions.bonesPerGeometry = addonPrefs.bonesPerGeometry
        uExportOptions.bonesPerVertex = addonPrefs.bonesPerVertex
        uExportOptions.clampBoundingBox = settings.clampBoundingBox

        if DEBUG: ttt = time.time() #!TIME
        UrhoExport(tData, uExportOptions, uExportData, settings.errorsMem)
        if DEBUG: print("[TIME] Export in {:.4f} sec".format(time.time() - ttt) ) #!TIME
        if DEBUG: ttt = time.time() #!TIME

        uScene.Load(uExportData, tData.blenderObjectName, sOptions)
        for uModel in uExportData.models:
            obj = None
            try:
                obj = bpy.data.objects[uModel.name]
                uModel.isEmpty=obj.type=="EMPTY" or (sOptions.wiredAsEmpty and obj.display_type=="WIRE")
                if uModel.isEmpty:
                    uModel.meshName=obj.name
                else:
                    if obj.lodsetID>0:
                        lodset = getLodSetWithID(obj.lodsetID)
                        uModel.meshName=lodset.name
                    elif tOptions.meshNameDerivedBy == 'Object':
                        uModel.meshName=uModel.name
                    else:
                        uModel.meshName=obj.data.name

                    if settings.generateModelNamePrefix:
                        uModel.meshName=PrefixFile(uModel.meshName)

            except:
                uModel.meshName=uModel.name
                uModel.isEmpty=False
            #
            ########

            # check if the draw_type is on wire=>skip
            # check if we already exported this mesh. if yes, skip it
            filepath = GetFilepath(PathType.MODELS, uModel.meshName, fOptions)
            uScene.AddFile(PathType.MODELS, uModel.name, filepath[1])

            print("%s: hasLOD:%s\n" % (uModel.meshName, str(tData.hasLODs)))
            # make sure that meshes with LOD gets written also there is a mesh with this name (that was created by a node that is referencing the root-mesh)
            if obj==None or (not uModel.isEmpty and (not uModel.meshName in processedMeshes or tData.hasLODs)):
                # use the name of the mesh to make mesh sharing possible (no need to write one shared mesh multiple times)
                if uModel.geometries:
                    if CheckFilepath(filepath[0], fOptions):
                        log.info( "Creating model {:s}".format(filepath[1]) )
                        UrhoWriteModel(uModel, filepath[0])
                        # mark this mesh to be processed and avoid another export
                        processedMeshes.append(uModel.meshName)
            
        for uAnimation in uExportData.animations:
            filepath = GetFilepath(PathType.ANIMATIONS, uAnimation.name, fOptions)
            uScene.AddFile(PathType.ANIMATIONS, uAnimation.name, filepath[1])
            if CheckFilepath(filepath[0], fOptions):
                log.info( "Creating animation {:s}".format(filepath[1]) )
                UrhoWriteAnimation(uAnimation, filepath[0])

            if uAnimation.triggers:
                filepath = GetFilepath(PathType.TRIGGERS, uAnimation.name, fOptions)
                uScene.AddFile(PathType.TRIGGERS, uAnimation.name, filepath[1])
                if CheckFilepath(filepath[0], fOptions):
                    log.info( "Creating triggers {:s}".format(filepath[1]) )
                    UrhoWriteTriggers(uAnimation.triggers, filepath[0], fOptions)
                
        for uMaterial in uExportData.materials:
            for textureName in uMaterial.getTextures():
                # Check the texture name (it can be a filename)
                if textureName is None:
                    continue
                # Check if the Blender image data exists
                image = bpy.data.images[textureName]
                if image is None:
                    continue
                # Get the texture file full path
                srcFilename = bpy.path.abspath(image.filepath)
                # Get image filename
                filename = os.path.basename(image.filepath)
                if not filename:
                    filename = textureName
                # Get the destination file full path (preserve the extension)
                fOptions.preserveExtTemp = True
                filepath = GetFilepath(PathType.TEXTURES, filename, fOptions)
                # Check if already exported
                if not uScene.AddFile(PathType.TEXTURES, textureName, filepath[1]):
                    continue
                # Copy or unpack the texture
                if settings.textures and CheckFilepath(filepath[0], fOptions):
                    if image.packed_file:
                        format = str(context.scene.render.image_settings.file_format)
                        mode = str(context.scene.render.image_settings.color_mode)
                        log.info( "Unpacking {:s} {:s} texture to {:s}".format(format, mode, filepath[1]) )
                        render_ext = context.scene.render.file_extension
                        file_ext = os.path.splitext(filepath[0])[1].lower()
                        if file_ext and render_ext != file_ext:
                            log.warning( "Saving texture as {:s} but the file has extension {:s}".format(render_ext, file_ext) )
                        image.save_render(filepath[0])
                    elif not os.path.exists(srcFilename):
                        log.error( "Missing source texture {:s}".format(srcFilename) )
                    else:
                        try:
                            log.info( "Copying texture {:s}".format(filepath[1]) )
                            shutil.copyfile(src = srcFilename, dst = filepath[0])
                        except:
                            log.error( "Cannot copy texture to {:s}".format(filepath[0]) )


                    
            # if settings.materialsList:
            #     for uModel in uExportData.models:
            #         filepath = GetFilepath(PathType.MATLIST, uModel.name, fOptions)
            #         uScene.AddFile(PathType.MATLIST, uModel.name, filepath[1])
            #         if CheckFilepath(filepath[0], fOptions):
            #             log.info( "Creating materials list {:s}".format(filepath[1]) )
            #             UrhoWriteMaterialsList(uScene, uModel, filepath[0])

        if DEBUG: print("[TIME] Write in {:.4f} sec".format(time.time() - ttt) ) #!TIME

    settings.errorsMem.Cleanup()
    if settings.selectErrors:
        selectErrors(context, settings.errorsMem, 'ALL')
    
    # Export scene and nodes
    UrhoExportScene(context, uScene, sOptions, fOptions)


    # reset data from before....
    return True


def ExecuteAddon(context, silent=False, ignoreGeoAnim=False, onlySelectedMesh=False):
    UpdateCheck.saving = True

    global_settings = bpy.data.worlds[0].global_settings

    export_no_geo_afterwards = False

    if global_settings.file_id == -1:
        global_settings.file_id = random.randrange(100,999)

    settings = bpy.context.scene.urho_exportsettings

    before_export_geo =  settings.geometries
    before_export_anim = settings.animations
    before_export_skel = settings.skeletons
    before_export_morph = settings.morphs
    before_export_source = settings.source

    if ignoreGeoAnim:
        settings.geometries = False
        settings.animations = False
        #settings.skeletons = False
        settings.morphs = False
    elif onlySelectedMesh:
        settings.source = "ONLY_SELECTED"
        settings.scenePrefab = False
        export_no_geo_afterwards = True
        settings.geometries = True

    before_export_selection = bpy.context.selected_objects
    before_export_active_obj = bpy.context.active_object
    
    before_export_mode = "OBJECT"
    if before_export_active_obj:
        try:
            before_export_mode = bpy.context.active_object.mode
        except:
            pass            

    startTime = time.time()
    print("----------------------Urho export start----------------------")    
    ExecuteUrhoExport(context)

    log.setLevel(logging.DEBUG)

    print ("TRY TO REMOVE TEMPOBJECTS:")
    for tempObj in tempObjects:
        print("REMOVE tempobject:%s" % tempObj.name)
        bpy.data.objects.remove(tempObj, do_unlink=True)
        pass
    tempObjects.clear()

    try:
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    except:
        pass        
    bpy.ops.object.select_all(action='DESELECT')
    for select_obj in before_export_selection:
        select_obj.select_set(True)
    bpy.context.view_layer.objects.active = before_export_active_obj
    #bpy.ops.object.mode_set(mode=before_export_mode, toggle=False)


    settings.geometries = before_export_geo
    settings.animations = before_export_anim
    settings.skeletons = before_export_skel
    settings.morphs = before_export_morph
    settings.source = before_export_source
    settings.scenePrefab = True
    
    if export_no_geo_afterwards:
        ExecuteAddon(context, True, True, False)


    log.info("Export ended in {:.4f} sec".format(time.time() - startTime) )
    
    if not silent:
        bpy.ops.urho.report('INVOKE_DEFAULT')

    UpdateCheck.saving = False


            
if __name__ == "__main__":
	register()

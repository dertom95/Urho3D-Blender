import bpy
import bgl
import json
import ctypes
import math
from bpy_extras import view3d_utils
from threading import current_thread

# connect to blender connect if available
from .utils import IsBConnectAddonAvailable, execution_queue, vec2dict, matrix2dict

BCONNECT_AVAILABLE = IsBConnectAddonAvailable()

if BCONNECT_AVAILABLE:
    import addon_blender_connect
    from addon_blender_connect.BConnectNetwork import Publish,StartNetwork,NetworkRunning,AddListener
    print("BCONNECT AVAILABLE! Starting network")
    StartNetwork()
else:
    print("BCONNECT UNAVAILABLE")


class UrhoRenderEngine(bpy.types.RenderEngine):

    # These three members are used by blender to set up the
    # RenderEngine; define its internal name, visible name and capabilities.
    bl_idname = "URHO3D"
    bl_label = "Urho3D"
    bl_use_preview = True

    ID_COUNTER = 0
    RENDERVIEWS = {}

    @staticmethod
    def NextID():
        UrhoRenderEngine.ID_COUNTER = UrhoRenderEngine.ID_COUNTER + 1
        return UrhoRenderEngine.ID_COUNTER
    # Init is called whenever a new render engine instance is created. Multiple
    # instances may exist at the same time, for example for a viewport and final
    # render.
    def __init__(self):
        self.scene_data = None
        self.draw_data = None
        self.ID = UrhoRenderEngine.NextID()
        self.region = None
        self.space_view3d = None
        self.scene = None

        UrhoRenderEngine.RENDERVIEWS[self.ID] = self

        # the current data, sent to the renderer. use this to detect changes
        self.renderViewData = {
            "viewId" : self.ID,
            "width" : 0,
            "height" : 0,
            "current_view_matrix" : None,
            "current_scene_name" : None
        }

        if BCONNECT_AVAILABLE:
            AddListener("runtime-%s" % self.ID,self.OnRuntimeMessage)
            AddListener("runtime",self.BConnectListener)
            
    # When the render engine instance is destroy, this is called. Clean up any
    # render engine data here, for example stopping running render threads.
    def __del__(self):
        changes = {"viewId" : self.ID,
                   "action" : "destroy"}
        changesJson = json.dumps(changes, indent=4)
        print("changesJson: %s" % changesJson)
        netData = str.encode(changesJson)

        Publish("blender","data_change","json",netData)            

    # messages from the runtime to this
    def OnRuntimeMessage(self,topic,subtype,meta,data):
        def QueuedExecution():
            print("OnRuntimeMessage(%s): Topic:%s subtype:%s meta:'%s' data-len:%s" % (self.ID,topic,subtype,meta,len(data)))
            if subtype == "draw":
                if self.draw_data:
                    self.draw_data.pixels = bgl.Buffer(bgl.GL_BYTE, len(data), data)
                    self.draw_data.updateTextureOnDraw = True
                    print("draw_data finished")
                    self.tag_redraw()
        execution_queue.execute_or_queue_action(QueuedExecution)

    # dummy. remove soon
    def BConnectListener(self,topic,subtype,meta,data):
        print("TOPIC2:%s subtype:%s" % (topic,subtype))
        print("DATALEN %s" % len(data))     

    # check the current blender-data and publish changes
    def update_data(self,region,space_view3d,scene):
        print("update-data")
        self.region = region
        self.space_view3d = space_view3d
        self.scene = scene

        data = self.renderViewData
        changes = {}

        
        forceMatrix = False

        # check screen resolution
        if data["width"]!=region.width or data["height"]!=region.height:
            data["width"] = region.width
            data["height"] = region.height
            changes["resolution"]={ 'width' : region.width, 'height' : region.height }
            forceMatrix = True

        # check view matrix
        region3d = space_view3d.region_3d

        ray_vector = view3d_utils.region_2d_to_vector_3d(region, region3d, (0, 0))
        view_camera_loc = region3d.view_matrix.inverted().translation
        look_at = region3d.view_location
        view_local_z = look_at - view_camera_loc
        fov2 = math.degrees(view_local_z.angle(ray_vector))


        vmat_inv = region3d.view_matrix.inverted()
        pmat = region3d.perspective_matrix @ vmat_inv
        fov = 2.0*math.atan(1.0/pmat[1][1])*180.0/math.pi; 

        #aspect = pmat[1][1]/prj[0][0]

        if (forceMatrix or data["current_view_matrix"] != region3d.view_matrix):
            data["current_view_matrix"] = region3d.view_matrix.copy()
            changes["view_matrix"]=matrix2dict(region3d.view_matrix)
            vm = region3d.view_matrix
            changes["view_matrix_euler"] = vec2dict(vm.to_euler(),True)
            changes["view_matrix_trans"] = vec2dict(vm.to_translation())
            changes["view_matrix_scale"] = vec2dict(vm.to_scale())
            changes["view_location"]=vec2dict(region3d.view_location)
            changes["view_rotation"]=vec2dict(region3d.view_rotation)
            changes["view_perspective_type"]=str(region3d.view_perspective)
            changes["perspective_matrix"]=matrix2dict(region3d.perspective_matrix);
            changes["fov"]=fov
            changes["fov2"]=fov2



            
        # check for scene-change
        if (data["current_scene_name"]!=scene.name):
            data["current_scene_name"]=scene.name
            changes["scene_name"]=scene.name

        if len(changes)>0:
            changes["view_id"] = data["viewId"]

            changesJson = json.dumps(changes, indent=4)
            print("changesJson: %s" % changesJson)
            data = str.encode(changesJson)

            Publish("blender","data_change","json",data)
        else:
            print("no changes")




    # This is the method called by Blender for both final renders (F12) and
    # small preview for materials, world and lights.
    def render(self, depsgraph):
        scene = depsgraph.scene
        scale = scene.render.resolution_percentage / 100.0
        self.size_x = int(scene.render.resolution_x * scale)
        self.size_y = int(scene.render.resolution_y * scale)

        # Fill the render result with a flat color. The framebuffer is
        # defined as a list of pixels, each pixel itself being a list of
        # R,G,B,A values.
        if self.is_preview:
            color = [0.1, 0.2, 0.1, 1.0]
        else:
            color = [0.2, 0.1, 0.1, 1.0]

        pixel_count = self.size_x * self.size_y
        rect = [color] * pixel_count

        # Here we write the pixel values to the RenderResult
        result = self.begin_result(0, 0, self.size_x, self.size_y)
        layer = result.layers[0].passes["Combined"]
        layer.rect = rect
        self.end_result(result)

    # For viewport renders, this method gets called once at the start and
    # whenever the scene or 3D viewport changes. This method is where data
    # should be read from Blender in the same thread. Typically a render
    # thread will be started to do the work while keeping Blender responsive.
    def view_update(self, context, depsgraph):
        region = context.region
        view3d = context.space_data
        scene = depsgraph.scene

        print("VIEWUPDATE(%s): region:%s view3d:%s scene:%s"%(self.ID,type(region),type(view3d),scene.name))


        # Get viewport dimensions
        dimensions = region.width, region.height

        if not self.scene_data:
            # First time initialization
            self.scene_data = []
            first_time = True

            # Loop over all datablocks used in the scene.
            for datablock in depsgraph.ids:
                pass
        else:
            first_time = False

            # Test which datablocks changed
            for update in depsgraph.updates:
                print("Datablock updated: ", update.id.name)

            # Test if any material was added, removed or changed.
            if depsgraph.id_type_updated('MATERIAL'):
                print("Materials updated")

        # Loop over all object instances in the scene.
        if first_time or depsgraph.id_type_updated('OBJECT'):
            for instance in depsgraph.object_instances:
                pass

    # For viewport renders, this method is called whenever Blender redraws
    # the 3D viewport. The renderer is expected to quickly draw the render
    # with OpenGL, and not perform other expensive work.
    # Blender will draw overlays for selection and editing on top of the
    # rendered image automatically.
    def view_draw(self, context, depsgraph):
        region = context.region
        scene = depsgraph.scene
        view3d = context.space_data


        print("view_draw(%s): region:%s view3d:%s scene:%s"%(self.ID,type(region),type(view3d),scene.name))
        self.update_data(region,view3d,scene)

        # Get viewport dimensions
        dimensions = region.width, region.height

        

        # Bind shader that converts from scene linear to display space,
        bgl.glEnable(bgl.GL_BLEND)
        bgl.glBlendFunc(bgl.GL_ONE, bgl.GL_ONE_MINUS_SRC_ALPHA);
        self.bind_display_space_shader(scene)

        if not self.draw_data or self.draw_data.dimensions != dimensions:
            self.draw_data = CustomDrawData(dimensions)

        self.draw_data.draw()

        self.unbind_display_space_shader()
        bgl.glDisable(bgl.GL_BLEND)


class CustomDrawData:
    def __init__(self, dimensions):
        # Generate dummy float image buffer
        self.dimensions = dimensions
        width, height = dimensions

        print("NEW CUSTOMDRAWDATA with resolution %s:%s" %( width,height ))

        self.pixels = [255,255,0,255] * width * height
        self.pixels = bgl.Buffer(bgl.GL_BYTE, width * height * 4, self.pixels)

        # Generate texture
        self.updateTextureOnDraw = False
        self.texture = bgl.Buffer(bgl.GL_INT, 1)
        bgl.glGenTextures(1, self.texture)
        bgl.glActiveTexture(bgl.GL_TEXTURE0)
        bgl.glBindTexture(bgl.GL_TEXTURE_2D, self.texture[0])
        bgl.glTexImage2D(bgl.GL_TEXTURE_2D, 0, bgl.GL_RGBA, width, height, 0, bgl.GL_RGBA, bgl.GL_UNSIGNED_BYTE, self.pixels)
        bgl.glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_TEXTURE_MIN_FILTER, bgl.GL_LINEAR)
        bgl.glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_TEXTURE_MAG_FILTER, bgl.GL_LINEAR)
        bgl.glBindTexture(bgl.GL_TEXTURE_2D, 0)

        # Bind shader that converts from scene linear to display space,
        # use the scene's color management settings.
        shader_program = bgl.Buffer(bgl.GL_INT, 1)
        bgl.glGetIntegerv(bgl.GL_CURRENT_PROGRAM, shader_program);

        # Generate vertex array
        self.vertex_array = bgl.Buffer(bgl.GL_INT, 1)
        bgl.glGenVertexArrays(1, self.vertex_array)
        bgl.glBindVertexArray(self.vertex_array[0])

        texturecoord_location = bgl.glGetAttribLocation(shader_program[0], "texCoord");
        position_location = bgl.glGetAttribLocation(shader_program[0], "pos");

        bgl.glEnableVertexAttribArray(texturecoord_location);
        bgl.glEnableVertexAttribArray(position_location);

        # Generate geometry buffers for drawing textured quad
        position = [0.0, 0.0, width, 0.0, width, height, 0.0, height]
        position = bgl.Buffer(bgl.GL_FLOAT, len(position), position)
        texcoord = [0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0]
        texcoord = bgl.Buffer(bgl.GL_FLOAT, len(texcoord), texcoord)

        self.vertex_buffer = bgl.Buffer(bgl.GL_INT, 2)

        bgl.glGenBuffers(2, self.vertex_buffer)
        bgl.glBindBuffer(bgl.GL_ARRAY_BUFFER, self.vertex_buffer[0])
        bgl.glBufferData(bgl.GL_ARRAY_BUFFER, 32, position, bgl.GL_STATIC_DRAW)
        bgl.glVertexAttribPointer(position_location, 2, bgl.GL_FLOAT, bgl.GL_FALSE, 0, None)

        bgl.glBindBuffer(bgl.GL_ARRAY_BUFFER, self.vertex_buffer[1])
        bgl.glBufferData(bgl.GL_ARRAY_BUFFER, 32, texcoord, bgl.GL_STATIC_DRAW)
        bgl.glVertexAttribPointer(texturecoord_location, 2, bgl.GL_FLOAT, bgl.GL_FALSE, 0, None)

        bgl.glBindBuffer(bgl.GL_ARRAY_BUFFER, 0)
        bgl.glBindVertexArray(0)

    def __del__(self):
        bgl.glDeleteBuffers(2, self.vertex_buffer)
        bgl.glDeleteVertexArrays(1, self.vertex_array)
        bgl.glBindTexture(bgl.GL_TEXTURE_2D, 0)
        bgl.glDeleteTextures(1, self.texture)

    def updateTexture(self):
        print("UPDATE TEXTURE")
        bgl.glActiveTexture(bgl.GL_TEXTURE0)
        bgl.glBindTexture(bgl.GL_TEXTURE_2D, self.texture[0])
        width, height = self.dimensions
        bgl.glTexImage2D(bgl.GL_TEXTURE_2D, 0, bgl.GL_RGBA, width, height, 0, bgl.GL_RGBA, bgl.GL_UNSIGNED_BYTE, self.pixels)

        #bgl.glTexImage2D(bgl.GL_TEXTURE_2D, 0, bgl.GL_RGBA16F, self.dimensions.width, self.dimensions.height, 0, bgl.GL_RGBA, bgl.GL_FLOAT, self.pixels)
        bgl.glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_TEXTURE_MIN_FILTER, bgl.GL_LINEAR)
        bgl.glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_TEXTURE_MAG_FILTER, bgl.GL_LINEAR)
        bgl.glBindTexture(bgl.GL_TEXTURE_2D, 0)

    def draw(self):
        if self.updateTextureOnDraw:
            self.updateTexture()
            self.updateTextureOnDraw = False

        bgl.glActiveTexture(bgl.GL_TEXTURE0)
        bgl.glBindTexture(bgl.GL_TEXTURE_2D, self.texture[0])
        bgl.glBindVertexArray(self.vertex_array[0])
        bgl.glDrawArrays(bgl.GL_TRIANGLE_FAN, 0, 4);
        bgl.glBindVertexArray(0)
        bgl.glBindTexture(bgl.GL_TEXTURE_2D, 0)


# RenderEngines also need to tell UI Panels that they are compatible with.
# We recommend to enable all panels marked as BLENDER_RENDER, and then
# exclude any panels that are replaced by custom panels registered by the
# render engine, or that are not supported.
def get_panels():
    exclude_panels = {
        'VIEWLAYER_PT_filter',
        'VIEWLAYER_PT_layer_passes',
    }

    panels = []
    for panel in bpy.types.Panel.__subclasses__():
        if hasattr(panel, 'COMPAT_ENGINES') and 'BLENDER_RENDER' in panel.COMPAT_ENGINES:
            if panel.__name__ not in exclude_panels:
                panels.append(panel)

    return panels

def register():
    # Register the RenderEngine
    bpy.utils.register_class(CustomRenderEngine)

    for panel in get_panels():
        panel.COMPAT_ENGINES.add('CUSTOM')

def unregister():
    bpy.utils.unregister_class(CustomRenderEngine)

    for panel in get_panels():
        if 'CUSTOM' in panel.COMPAT_ENGINES:
            panel.COMPAT_ENGINES.remove('CUSTOM')
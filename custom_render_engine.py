import bpy
import os
import json
import ctypes
import math
from bpy_extras import view3d_utils
from threading import current_thread
import weakref
from mathutils import Vector
import sys
import gpu
from gpu_extras.batch import batch_for_shader
import numpy as np
import time

try:
    from PIL import Image,ImageDraw
except:
    import bpy,subprocess
    pybin = sys.executable
    subprocess.check_call([pybin, '-m', 'ensurepip'])
    subprocess.check_call([pybin, '-m', 'pip', 'install', 'Pillow'])
    from PIL import Image,ImageDraw

# connect to blender connect if available
from .utils import execution_queue, vec2dict, matrix2dict, PingForRuntime

from .addon_blender_connect.BConnectNetwork import Publish,StartNetwork,NetworkRunning,AddListener, GetSessionId

class ViewRenderer:
    def __init__(self,id,topic,renderengine):
        self.view_id = id
        self.renderEngine = weakref.ref(renderengine)
        self.topic = topic
        AddListener(self.topic,self.OnRuntimeMessage)

    def set_renderengine(self,renderengine):
        self.renderEngine = weakref.ref(renderengine)

    def OnRuntimeMessage(self,topic,subtype,meta,data):
        print("##DRAW MESSAGE %s" % topic)
        def QueuedExecution():
            print("--1")
            if not self.renderEngine or self.renderEngine() is None:
                self.renderEngine = None
                return

            print("MESSAGE START")
            print("OnRuntimeMessage(%s): Topic:%s subtype:%s meta:'%s' data-len:%s" % (self.view_id,topic,subtype,meta,len(data)))
            if subtype == "draw":
                if self.renderEngine().draw_data:
                    if len(data) % 4 != 0:
                        raise ValueError("The byte string length must be a multiple of 4 for RGBA data.")


                    print ("Convert ImageData!")
                    start_time = time.time()

                    byte_array = np.frombuffer(data, dtype=np.uint8)

                    # Normalize the values to the range [0.0, 1.0] and convert to float32
                    float_array = byte_array.astype(np.float32) / 255.0

                    self.renderEngine().draw_data.pixels = float_array.flatten().tolist()
    
                        # Stop the stopwatch
                    end_time = time.time()


                    # Calculate elapsed time
                    elapsed_time = end_time - start_time
                    print (f"Finished Convert ImageData! Took {elapsed_time:.6f}s")

                    #self.renderEngine().draw_data.pixels_dim = meta.
                    # normalized_floats = np.frombuffer(data, dtype=np.uint8) / 255.0

                    # # Convert the normalized floats to float16
                    # float16_array = normalized_floats.astype(np.float16)
                   
                    # self.renderEngine().draw_data.pixels = gpu.types.Buffer('FLOAT', len(float16_array), float16_array)
                    #self.renderEngine().draw_data.pixels = bgl.Buffer(bgl.GL_BYTE, len(data), data)
                    self.renderEngine().draw_data.updateTextureOnDraw = True
                    execution_queue.execute_or_queue_action(self.renderEngine().draw_data.update)    
                    print("draw_data finished")
                    self.renderEngine().tag_redraw()

        execution_queue.execute_or_queue_action(QueuedExecution)        
    

class UrhoRenderEngine(bpy.types.RenderEngine):

    # These three members are used by blender to set up the
    # RenderEngine; define its internal name, visible name and capabilities.
    bl_idname = "URHO3D"
    bl_label = "Urho3D"
    bl_use_preview = True

    
    ID_COUNTER = 0
    RENDERVIEWS_IDS = {}

    @staticmethod
    def NextID():
        UrhoRenderEngine.ID_COUNTER = UrhoRenderEngine.ID_COUNTER+1
        return UrhoRenderEngine.ID_COUNTER

    # Init is called whenever a new render engine instance is created. Multiple
    # instances may exist at the same time, for example for a viewport and final
    # render.
    def __init__(self):
        self.scene_data = None
        self.draw_data = None
        #self.view_id = UrhoRenderEngine.NextID()
        self.view_id = 0
        self.region = None
        self.space_view3d = None
        self.scene = None
        self.viewRenderer = None
        self.forceUpdate = False
        self.changes = None

        
        print("##########-############-###########-###########")
        print("##########-############-###########-###########")
        print("##########-############-###########-###########")
        print("CREATED RenderEngine %s " % (type(self)))

        # the current data, sent to the renderer. use this to detect changes
        self.renderViewData = {
            "view_id" : 0,
            "width" : 0,
            "height" : 0,
            "current_view_matrix" : None,
            "current_scene_name" : None,
            "current_view_distance" : None,
            "export_path" : None,
            "pos" : None,
            "dir" : None,
            "clip_start" : 0,
            "clip_end" : 0,
            "frame_current" : 0
        }

        execution_queue.execute_or_queue_action(PingForRuntime)
        AddListener("runtime",self.OnRuntimeMessage)     

    def OnRuntimeMessage(self,topic,subtype,meta,data):
        #print("##runtime mesg %s/%s" % (topic,subtype) )
        def QueuedExecution():
            #print("FORTY:")
            #print("##runtime mesg %s/%s" % (topic,subtype) )

            if topic == "runtime" and subtype == "hello":
                print("FORCE UPDATE  FORCE UPDATE  FORCE UPDATE  FORCE UPDATE  FORCE UPDATE  FORCE UPDATE  FORCE UPDATE  ")
                self.forceUpdate = True
                self.tag_redraw()

        execution_queue.execute_or_queue_action(QueuedExecution)  
            
    # When the render engine instance is destroy, this is called. Clean up any
    # render engine data here, for example stopping running render threads.
    def __del__(self):
        print("###############################################################")
        print("DELETEDELETE %s" % type(self))
        # changes = {"viewId" : self.view_id,
        #            "action" : "destroy"}
        # changesJson = json.dumps(changes, indent=4)
        # print("changesJson: %s" % changesJson)
        # netData = str.encode(changesJson)

        # Publish("blender","data_change","json",netData)            

    # messages from the runtime to this


 

    # check the current blender-data and publish changes
    def update_data(self,region,space_view3d,scene):
        #print("update-data %s" % self.view_id)
        self.region = region
        self.space_view3d = space_view3d
        self.scene = scene

    #    print("pointers region:%s space_view:%s" % (region.as_pointer(),space_view3d.as_pointer()))

        if self.view_id == 0:
     #       print("SV3D TYPE %s" % type(self.space_view3d.region_3d))

            if region in UrhoRenderEngine.RENDERVIEWS_IDS:
                viewRenderer = UrhoRenderEngine.RENDERVIEWS_IDS[region]
                self.view_id = viewRenderer.view_id
                viewRenderer.set_renderengine(self)
      #          print("REVIVED")
            else:
       #         print("NEW")
                self.view_id = UrhoRenderEngine.NextID()
                newRenderer = ViewRenderer(self.view_id,"runtime-%s-%s"%(GetSessionId(),self.view_id),self)
                UrhoRenderEngine.RENDERVIEWS_IDS[region]=newRenderer

        #    print("### GOT AN ID:%s ###" % self.view_id)

            self.renderViewData["view_id"]=self.view_id

                #AddListener("runtime",self.BConnectListener)


        data = self.renderViewData
        
        
        forceMatrix = False

        # check screen resolution
        if data["width"]!=region.width or data["height"]!=region.height:
             forceMatrix = True

        # check view matrix
        region3d = space_view3d.region_3d

        region3d.view_perspective = 'PERSP'


        vmat_inv = region3d.view_matrix.inverted()
        pmat = region3d.perspective_matrix @ vmat_inv
        fov = 2.0*math.atan(1.0/pmat[1][1])*180.0/math.pi; 

        #aspect = pmat[1][1]/prj[0][0]

        #print("UPDATE DATA! FORCED:%s",self.forceUpdate)

        if not self.changes:
            self.changes = {}

        changed = False

        direction = region3d.view_rotation @ Vector((0.0, 0.0, -1.0))
        top = region3d.view_rotation @ Vector((0.0, 1.0, 0.0))
        pos = view3d_utils.region_2d_to_origin_3d(region, region3d, (region.width/2.0, region.height/2.0))

        if (self.forceUpdate or forceMatrix 
                or data["frame_current"] != scene.frame_current
                or data["current_view_matrix"] != region3d.view_matrix 
                or data["pos"]!=pos or data["dir"]!=direction
                or (region3d.view_perspective=="ORTHO" and data["current_view_distance"]!=region3d.view_distance)):
            data["current_view_matrix"] = region3d.view_matrix.copy()
            data["current_view_distance"] = region3d.view_distance
            data["dir"]=direction
            data["pos"]=pos

            self.changes["view_matrix"]=matrix2dict(region3d.view_matrix)
            vm = region3d.view_matrix
            #changes["view_matrix_euler"] = vec2dict(vm.to_euler(),True)
            #changes["view_matrix_trans"] = vec2dict(vm.to_translation())
            #changes["view_matrix_scale"] = vec2dict(vm.to_scale())
            #changes["view_location"]=vec2dict(region3d.view_location)
            #changes["view_rotation"]=vec2dict(region3d.view_rotation)
            self.changes["view_perspective_type"]=str(region3d.view_perspective)
            self.changes["perspective_matrix"]=matrix2dict(region3d.perspective_matrix);
            self.changes["fov"]=fov
            self.changes["view_distance"]=region3d.view_distance
    
            if data["frame_current"] != scene.frame_current:
                self.changes["scene_time"] = (scene.frame_current-1) / scene.render.fps
            data["frame_current"] = scene.frame_current

            

            self.changes["view_direction"]=vec2dict(direction)
            self.changes["view_up"]=vec2dict(top)
            self.changes["view_position"]=vec2dict(pos)

            #print("pos:%s type:%s dir:%s top:%s" %(str(pos),type(pos),direction,top))
            
            self.forceUpdate = False
            changed = True



            
        # check for scene-change
        #if (data["current_scene_name"]!=scene.name):


        urho_settings = scene.urho_exportsettings

#        if (data["export_path"] != export_path):

        if changed:
            self.changes["view_id"] = data["view_id"]
            self.changes["session_id"] = GetSessionId()


            export_path = urho_settings.outputPath
            self.changes["export_path"] = export_path
            data["export_path"] = export_path

            data["current_scene_name"]=scene.name
            self.changes["scene_name"]=scene.name

            data["width"] = region.width
            data["height"] = region.height
            self.changes["clip_start"]=space_view3d.clip_start
            self.changes["clip_end"]=space_view3d.clip_end
            
            self.changes["resolution"]={ 'width' : region.width, 'height' : region.height }

            self.tag_redraw()
            #print("CHANGED")
        else:
            if self.changes:
                changesJson = json.dumps(self.changes, indent=4)
                #print("changesJson: %s" % changesJson)
                data = str.encode(changesJson)

                Publish("blender","data_change","json",data)

                # def call_on_queue():
                #     bpy.ops.urho.export(ignore_geo_skel_anim=True)

                # execution_queue.execute_or_queue_action(call_on_queue)

                self.changes = None
            #print("no changes")




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

        #print("VIEWUPDATE(%s): region:%s view3d:%s scene:%s"%(self.view_id,type(region),type(view3d),scene.name))

        # Get viewport dimensions
        dimensions = region.width, region.height

        if not self.scene_data:
            # First time initialization
            self.scene_data = []
            first_time = True

            # Loop over all datablocks used in the scene.
            # for datablock in depsgraph.ids:
            #     pass
        else:
            first_time = False

            # Test which datablocks changed
            for update in depsgraph.updates:
                print("Datablock updated: ", update.id.name)

            # Test if any material was added, removed or changed.
            if depsgraph.id_type_updated('MATERIAL'):
                print("Materials updated")

        # if not self.draw_data or self.draw_data.dimensions != dimensions:
        #     self.draw_data = CustomDrawData(dimensions)

        # self.draw_data.update()
        # Loop over all object instances in the scene.
        # if first_time or depsgraph.id_type_updated('OBJECT'):
        #     for instance in depsgraph.object_instances:
        #         pass

    # For viewport renders, this method is called whenever Blender redraws
    # the 3D viewport. The renderer is expected to quickly draw the render
    # with OpenGL, and not perform other expensive work.
    # Blender will draw overlays for selection and editing on top of the
    # rendered image automatically.
    def view_draw(self, context, depsgraph):
        region = context.region
        scene = depsgraph.scene
        view3d = context.space_data

        #print("view_draw(%s): region:%s view3d:%s scene:%s"%(self.view_id,type(region),type(view3d),scene.name))
        self.update_data(region,view3d,scene)

        # Get viewport dimensions
        dimensions = region.width, region.height

        # Bind shader that converts from scene linear to display space,
        # bgl.glEnable(bgl.GL_BLEND)
        # bgl.glBlendFunc(bgl.GL_ONE, bgl.GL_ONE_MINUS_SRC_ALPHA);
        # self.bind_display_space_shader(scene)

        # if not self.draw_data or self.draw_data.dimensions != dimensions:
        #     self.draw_data = CustomDrawData(dimensions)

        # self.draw_data.draw()

        # self.unbind_display_space_shader()
        # bgl.glDisable(bgl.GL_BLEND)
        gpu.state.blend_set('ALPHA_PREMULT')
        self.bind_display_space_shader(scene)

        if not self.draw_data or self.draw_data.dimensions != dimensions:
            self.draw_data = CustomDrawData(dimensions)

        self.draw_data.draw()

        self.unbind_display_space_shader()
        gpu.state.blend_set('NONE')        


urhoImage = Image.open(os.path.dirname(os.path.realpath(__file__))+"/res/urho3d.png","r")

class CustomDrawData:
    def __init__(self, dimensions):
        global urhoImage

        # Generate dummy float image buffer
        self.dimensions = dimensions
        width, height = dimensions

        print("NEW CUSTOMDRAWDATA with resolution %s:%s" %( width,height ))

        blank = Image.new('RGBA',(width,height),(100,100,100,255))
        blank.alpha_composite(urhoImage,dest=(int(width/2-urhoImage.width/2),int(height/2-urhoImage.height/2)))

        self.render_image = bpy.data.images.new(name="__renderer__",width=width,height=height)

        self.pixels = np.array(blank, dtype=np.float32)
        self.pixels /= 255.0
        self.pixels = self.pixels.flatten().tolist()

        self.updateTextureOnDraw = True
        execution_queue.queue_action(self.update)
        
        #self.pixels = [255,0,0,255] * width * height
        #self.pixels = list(blank.tobytes())
        #self.pixels = bgl.Buffer(bgl.GL_BYTE, width * height * 4, self.pixels)

        #convert from byte to float
        #self.pixels = np.array(self.pixels, dtype=np.float32) / 255.0

        #self.pixels = gpu.types.Buffer('FLOAT', width * height * 4, self.pixels)


        #self.texture = gpu.types.GPUTexture((width, height), format='RGBA16F', data=self.pixels)


        # Generate texture
        # self.texture = bgl.Buffer(bgl.GL_INT, 1)
        # bgl.glGenTextures(1, self.texture)
        # bgl.glActiveTexture(bgl.GL_TEXTURE0)
        # bgl.glBindTexture(bgl.GL_TEXTURE_2D, self.texture[0])
        # bgl.glTexImage2D(bgl.GL_TEXTURE_2D, 0, bgl.GL_RGBA, width, height, 0, bgl.GL_RGBA, bgl.GL_UNSIGNED_BYTE, self.pixels)
        # bgl.glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_TEXTURE_MIN_FILTER, bgl.GL_LINEAR)
        # bgl.glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_TEXTURE_MAG_FILTER, bgl.GL_LINEAR)
        # bgl.glBindTexture(bgl.GL_TEXTURE_2D, 0)

        # # Bind shader that converts from scene linear to display space,
        # # use the scene's color management settings.
        # shader_program = bgl.Buffer(bgl.GL_INT, 1)
        # bgl.glGetIntegerv(bgl.GL_CURRENT_PROGRAM, shader_program);

        # # Generate vertex array
        # self.vertex_array = bgl.Buffer(bgl.GL_INT, 1)
        # bgl.glGenVertexArrays(1, self.vertex_array)
        # bgl.glBindVertexArray(self.vertex_array[0])

        # texturecoord_location = bgl.glGetAttribLocation(shader_program[0], "texCoord")
        # position_location = bgl.glGetAttribLocation(shader_program[0], "pos")

        # bgl.glEnableVertexAttribArray(texturecoord_location);
        # bgl.glEnableVertexAttribArray(position_location);

        # # Generate geometry buffers for drawing textured quad
        # position = [0.0, 0.0, width, 0.0, width, height, 0.0, height]
        # position = bgl.Buffer(bgl.GL_FLOAT, len(position), position)
        # texcoord = [0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0]
        # texcoord = bgl.Buffer(bgl.GL_FLOAT, len(texcoord), texcoord)

        # self.vertex_buffer = bgl.Buffer(bgl.GL_INT, 2)

        # bgl.glGenBuffers(2, self.vertex_buffer)
        # bgl.glBindBuffer(bgl.GL_ARRAY_BUFFER, self.vertex_buffer[0])
        # bgl.glBufferData(bgl.GL_ARRAY_BUFFER, 32, position, bgl.GL_STATIC_DRAW)
        # bgl.glVertexAttribPointer(position_location, 2, bgl.GL_FLOAT, bgl.GL_FALSE, 0, None)

        # bgl.glBindBuffer(bgl.GL_ARRAY_BUFFER, self.vertex_buffer[1])
        # bgl.glBufferData(bgl.GL_ARRAY_BUFFER, 32, texcoord, bgl.GL_STATIC_DRAW)
        # bgl.glVertexAttribPointer(texturecoord_location, 2, bgl.GL_FLOAT, bgl.GL_FALSE, 0, None)

        # bgl.glBindBuffer(bgl.GL_ARRAY_BUFFER, 0)
        # bgl.glBindVertexArray(0)

    def __del__(self):
        if self.texture:
            del self.texture
        # bgl.glDeleteBuffers(2, self.vertex_buffer)
        # bgl.glDeleteVertexArrays(1, self.vertex_array)
        # bgl.glBindTexture(bgl.GL_TEXTURE_2D, 0)
        # bgl.glDeleteTextures(1, self.texture)

    def updateTexture(self):
        print("UPDATE TEXTURE")
        #old_texture = self.texture
        #gpu.texture.update(self.texture,self.pixels)

        start_time = time.time()

        self.render_image.pixels = self.pixels
        self.render_image.update()
        self.texture = gpu.texture.from_image(self.render_image)

        end_time = time.time()

        # Calculate elapsed time
        elapsed_time = end_time - start_time
        print (f"UPDATE TEXTURE! Took {elapsed_time:.6f}s")

        #self.texture = gpu.types.GPUTexture((self.texture.width, self.texture.height), format='RGBA16F', data=self.pixels)        
        #del old_texture
        #self.texture = gpu.types.GPUTexture((self.width, self.height), format='RGBA8', data=self.pixels)
        
        # bgl.glActiveTexture(bgl.GL_TEXTURE0)
        # bgl.glBindTexture(bgl.GL_TEXTURE_2D, self.texture[0])
        # width, height = self.dimensions
        # bgl.glTexImage2D(bgl.GL_TEXTURE_2D, 0, bgl.GL_RGBA, width, height, 0, bgl.GL_RGBA, bgl.GL_UNSIGNED_BYTE, self.pixels)

        # #bgl.glTexImage2D(bgl.GL_TEXTURE_2D, 0, bgl.GL_RGBA16F, self.dimensions.width, self.dimensions.height, 0, bgl.GL_RGBA, bgl.GL_FLOAT, self.pixels)
        # bgl.glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_TEXTURE_MIN_FILTER, bgl.GL_LINEAR)
        # bgl.glTexParameteri(bgl.GL_TEXTURE_2D, bgl.GL_TEXTURE_MAG_FILTER, bgl.GL_LINEAR)
        # bgl.glBindTexture(bgl.GL_TEXTURE_2D, 0)

    def update(self):
        if self.updateTextureOnDraw:
            self.updateTexture()
            self.updateTextureOnDraw = False

    def draw(self):

        if self.texture:
            from gpu_extras.presets import draw_texture_2d
            draw_texture_2d(self.texture, (0, self.texture.height), self.texture.width, -self.texture.height)

        # bgl.glActiveTexture(bgl.GL_TEXTURE0)
        # bgl.glBindTexture(bgl.GL_TEXTURE_2D, self.texture[0])
        # bgl.glBindVertexArray(self.vertex_array[0])
        # bgl.glDrawArrays(bgl.GL_TRIANGLE_FAN, 0, 4);
        # bgl.glBindVertexArray(0)
        # bgl.glBindTexture(bgl.GL_TEXTURE_2D, 0)


# RenderEngines also need to tell UI Panels that they are compatible with.
# We recommend to enable all panels marked as BLENDER_RENDER, and then
# exclude any panels that are replaced by custom panels registered by the
# render engine, or that are not supported.
def get_panels():
    # exclude_panels = {
    #     'VIEWLAYER_PT_filter',
    #     'VIEWLAYER_PT_layer_passes',
    # }

    # panels = []
    # for panel in bpy.types.Panel.__subclasses__():
    #     if hasattr(panel, 'COMPAT_ENGINES') and ('BLENDER_EEVEE' in panel.COMPAT_ENGINES or 'CYCLES' in panel.COMPAT_ENGINES):
    #         if panel.__name__ not in exclude_panels:
    #             panels.append(panel)

    panels = [
              bpy.types.DATA_PT_vertex_groups,
              bpy.types.DATA_PT_shape_keys,
              bpy.types.DATA_PT_uv_texture,
              bpy.types.DATA_PT_vertex_colors,
              bpy.types.DATA_PT_context_mesh,
              bpy.types.CYCLES_LIGHT_PT_light,
              bpy.types.DATA_PT_lens,
              bpy.types.WORLD_PT_context_world
              ]

    return panels

def register():    # Register the RenderEngine
    #bpy.utils.register_class(CustomRenderEngine)

    print("REGISTER PANEL")
    for panel in get_panels():
        #print("p:%s" % panel)
        panel.COMPAT_ENGINES.add('URHO3D')
    print("---done---")

def unregister():
    #bpy.utils.unregister_class(CustomRenderEngine)

    for panel in get_panels():
        if 'URHO3D' in panel.COMPAT_ENGINES:
            panel.COMPAT_ENGINES.remove('URHO3D')
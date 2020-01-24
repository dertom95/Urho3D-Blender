import bpy

from .utils import IsBConnectAddonAvailable, execution_queue, set_found_blender_runtime

BCONNECT_AVAILABLE = IsBConnectAddonAvailable()

if BCONNECT_AVAILABLE:
    import addon_blender_connect
    from addon_blender_connect.BConnectNetwork import Publish,StartNetwork,NetworkRunning,AddListener,GetSessionId
    print("BCONNECT AVAILABLE! Starting network")
    StartNetwork()

    def OnRuntimeMessage(topic,subtype,meta,data):
        #print("OnRuntimeMessage(%s): Topic:%s subtype:%s meta:'%s' data-len:%s" % (self.view_id,topic,subtype,meta,len(data)))
        def QueuedExecution():
            global FOUND_RUNTIME
            # if subtype == "component-update":
            #     print("Try to reload components: todo check if the current file is %s" % data)
            #     bpy.ops.nodetree.jsonload('EXEC_DEFAULT')
            print("INCOMING %s - %s - %s - %s" % ( topic,subtype,meta,data ) )
            if topic=="runtime" and subtype=="pong":
                set_found_blender_runtime(True)
            pass

        execution_queue.queue_action(QueuedExecution) 

    AddListener("runtime",OnRuntimeMessage)
    

else:
    print("BCONNECT UNAVAILABLE")






   


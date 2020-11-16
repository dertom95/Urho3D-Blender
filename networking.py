import bpy

from .utils import execution_queue, set_found_blender_runtime,PingData

from .addon_blender_connect.BConnectNetwork import Publish,StartNetwork,NetworkRunning,AddListener,GetSessionId
print("BCONNECT AVAILABLE! Starting network")

running = False

def Start():
    global running
    if running:
        print("Network already running")
        return

    running = True
    StartNetwork()

    def OnRuntimeMessage(topic,subtype,meta,data):
        #print("OnRuntimeMessage(%s): Topic:%s subtype:%s meta:'%s' data-len:%s" % (self.view_id,topic,subtype,meta,len(data)))
        def QueuedExecution():
            global FOUND_RUNTIME
            # if subtype == "component-update":
            #     print("Try to reload components: todo check if the current file is %s" % data)
            #     bpy.ops.nodetree.jsonload('EXEC_DEFAULT')
            #print("INCOMING %s - %s - %s - %s" % ( topic,subtype,meta,data ) )
            if topic=="runtime" and subtype=="pong":
                set_found_blender_runtime(True)
                PingData.ping_check_running = False

        execution_queue.queue_action(QueuedExecution) 

    AddListener("runtime",OnRuntimeMessage)


   


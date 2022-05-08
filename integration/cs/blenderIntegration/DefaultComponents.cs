using System;
using System.Collections.Generic;
using Urho;
using Urho.IO;
using Urho.Resources;

// ------------------------------------
// Helper Components used during export
// ------------------------------------
public class RotationFix : LogicComponent
{
    public RotationFix(IntPtr handle) : base(handle) { }
    [Preserve]
    public RotationFix() { }

    protected override void OnStart()
    {
        Node.Rotate(new Quaternion(90, 0, 90));
        Enabled = false;
    }

}

public class RenderData : Component
{
    public String RenderPath = "";
    public bool HDR = false;
    public bool Gamma = false;
    public bool Bloom = false;
    public bool FXAA2 = false;
    public bool sRGB = false;
    public RenderData(IntPtr handle) : base(handle) { }
    [Preserve]
    public RenderData() { }
}
public class GroupInstance : LogicComponent
{
    public String groupFilename;

    [Preserve]
    public GroupInstance(IntPtr handle) : base(handle) { }
    [Preserve]
    public GroupInstance() { }

    // TODO
    public override void OnAttachedToNode(Node node)
    {
        base.OnAttachedToNode(node);
        var file = Application.ResourceCache.GetXmlFile(groupFilename);
        if (file != null) {
            try {
                var groupRoot = new Node();
                groupRoot.LoadXml(file.GetRoot());
                foreach (var child in new List<Node>(groupRoot.Children)) {
                    Node.AddChild(child);
                }
            }
            catch (Exception e) {
                LogSharp.Error("Error", e);
            }
        }
    }

    protected override void OnStart()
    {
        base.OnStart();
    }
}
public class ParentBone : LogicComponent
{
    public ParentBone(IntPtr handle) : base(handle) { }
    [Preserve]
    public ParentBone() { }

    public string boneName;

    protected override void OnStart()
    {
        if (boneName == null || boneName == "") {
            return;
        }

        try {
            Node bone = Node.Parent.GetChild(boneName, true);
            if (bone != null) {
                Node.Parent = bone;
            }
        }
        catch (Exception e) {
            Log.Error("Bone-Error", e);
        }
    }
}

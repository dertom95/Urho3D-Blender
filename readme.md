Urho3D-Blender
==============

This plugin is **work in progress**....


**Use this:**
   
Wanna give it a try? **Download the latest release from the [release section](https://github.com/dertom95/Urho3D-Blender/releases)**

**Caution**: Just using github-zip won't work due to missing submodules and missing urho3d-runtime


* install plugin in blender
  * navigate to: edit->preferences->addons
  * ->'Install...'->[downloaddir]/urho3d-blender-exporter.zip and enable the checkbox

**Caution** Since this addon depends on pyzmq, pyzmq is installed automatically if not present. If blender makes problems try to execute blender (once) as admin  



**Additional**  
[Getting Started Video](https://www.youtube.com/watch?v=vyP0dXvh9Aw)  
[Video Playlist](https://www.youtube.com/playlist?list=PL3dUhaUzMSSq0ngtTH6f_cj7jKKRhtzdM)  
   
   
**INFO** If you struggle to install this addon, there is [another exporter](https://github.com/1vanK/Urho3D-Blender/tree/2_80) also based on reattiva's addon for blender 2.8+ that might worker better for you.   
     
   
   
   
[Blender](http://www.blender.org) to [Urho3D](https://urho3d.github.io) mesh exporter.

Caution: This version is highly experimental. Consider it proof of concept and WIP.

 
Also install and activate [addon_jsonnodetree](https://github.com/dertom95/addon_jsonnodetree) for support of setting components and adding materials 

Videos:
- [Install](https://www.youtube.com/watch?v=o-1RMIwQZMY)
- [Exporter Options](https://www.youtube.com/watch?v=VtZk6FipkdU)
- [runtime and material-nodes](https://www.youtube.com/watch?v=utLNqfxZ_KE)
- [materialnodes and textures](https://www.youtube.com/watch?v=13jslwWhUSk)
- [component nodes ](https://www.youtube.com/watch?v=Ni3nD5687aQ)
- [custom component workflow](https://www.youtube.com/watch?v=B37ZTa7mbpE)
- [Collection Instances](https://www.youtube.com/watch?v=Ut0HJYpvuFc)
- [Armature Animation](https://www.youtube.com/watch?v=h2NS348L8X0)


Development
===========

blender-addons **addon_jsonnodetree** and **addon_blender_connect** are now integrated into this addon as submodule. Both are still working standalone

* To clone:
  ```
  git clone --recurse-submodules  https://github.com/dertom95/Urho3D-Blender.git
  ```

* To update:
  ```
  git pull --recurse-submodules
  ```

* To build runtimes and create release.zip
  ```
  ./create_release.sh
  ```




------------------------------------------------------------------------------------  
------------------------------------------------------------------------------------  
OLD INSTRUCTIONS
------------------------------------------------------------------------------------  
------------------------------------------------------------------------------------  


Guide [here](https://github.com/reattiva/Urho3D-Blender/blob/master/guide.txt).

Installation:
- download the repository zip file        
![download](https://cloud.githubusercontent.com/assets/5704756/26752822/f5ebaecc-4858-11e7-8e7c-35082ee751d3.png)
- menu "File"
- select "User Preferences..."
- select page "Add-ons"
- click "Install from File..."        
![install](https://cloud.githubusercontent.com/assets/5704756/26752823/fd119d7e-4858-11e7-9795-5d3b9d1a895c.png)
- select the downloaded zip file
- enable the addon

The addon is located in the "Properties" panel, at the end of the "Render" page (camera icon):
![location](https://cloud.githubusercontent.com/assets/5704756/26752826/0145c014-4859-11e7-9eb3-15f1724f3d6e.png)

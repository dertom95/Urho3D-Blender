HOME=$PWD

rm -Rf runtimes
rm -Rf temp

mkdir -p runtimes
mkdir temp

cd temp

git clone https://github.com/dertom95/urho3d-blender-runtime-ver2
cd urho3d-blender-runtime-ver2/
./tools/build_win_lin.sh

cd $HOME

cp -R -L temp/urho3d-blender-runtime-ver2/build/native/bin/* runtimes
cp temp/urho3d-blender-runtime-ver2/build/mingw/bin/urho3d-blender-runtime.exe runtimes

rm -Rf temp
rm -Rf __pycache__

cd ..
zip -r $HOME/urho3d-blender-exporter.zip Urho3D-Blender -x '*.git*'
cd $HOME
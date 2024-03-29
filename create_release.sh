HOME=$PWD
FOLDER=${PWD##*/}

rm -Rf runtimes
rm -Rf temp
rm urho3d-blender-exporter.zip
rm urho3d-blender-cs-integration.zip

mkdir -p runtimes
mkdir temp

cd temp

git clone https://github.com/dertom95/urho3d-blender-runtime-ver2
cd urho3d-blender-runtime-ver2/
git submodule update --init
./tools/build_win_lin.sh

cd $HOME

cp -R -L temp/urho3d-blender-runtime-ver2/build/linux/bin/* runtimes
cp temp/urho3d-blender-runtime-ver2/build/mingw/bin/urho3d-blender-runtime.exe runtimes

rm -Rf temp
rm -Rf __pycache__

cd ..
zip -r $HOME/urho3d-blender-exporter.zip $FOLDER -x '*.git*' -x '*pycache*' -x */testing/\* 
cd $HOME/integration/cs && zip -r $HOME/urho3d-blender-cs-integration.zip blenderIntegration
cd $HOME

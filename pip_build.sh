pip3 list |grep wheel >& /dev/null || pip3 install wheel
[ -d build ] && rm -fr build
[ -d dist ] && rm -fr dist
[ -d kbmc.egg-info ] && rm -fr kbmc.egg-info
python3 setup.py sdist bdist_wheel
echo "Test"
sleep 1
tar tzf dist/*.tar.gz
twine check dist/*
#python -m build
# Install
#python -m pip install dist/xxx.whl

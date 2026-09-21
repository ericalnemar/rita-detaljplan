@echo off
rem Kör alla tester med QGIS egen Python. Sätt QGIS_ROOT för en annan installation.
if "%QGIS_ROOT%"=="" set "QGIS_ROOT=C:\Program Files\QGIS 4.2.2"
set QT_QPA_PLATFORM=offscreen
pushd "%~dp0.."
call "%QGIS_ROOT%\bin\python-qgis.bat" -m unittest discover -s tests -v
set RC=%ERRORLEVEL%
popd
exit /b %RC%

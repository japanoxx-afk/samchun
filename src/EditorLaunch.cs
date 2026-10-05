using System;
using System.IO;
using System.Diagnostics;
using System.Collections.Generic;

internal static class EditorLaunch {
 internal static ProcessStartInfo Prepare(string game) {
  game=Path.GetFullPath(game);
  if(!File.Exists(game))throw new FileNotFoundException("게임 파일을 찾을 수 없습니다.",game);
  string dir=Path.GetDirectoryName(game),editor=Path.Combine(dir,"3kd2Edit.exe");
  foreach(string name in new[]{"3kd2Edit.exe","3kd2edit.DBX","RES.PAK","PALETTE.PAK"})
   if(!File.Exists(Path.Combine(dir,name)))throw new FileNotFoundException("에디터 실행에 필요한 "+name+" 파일이 없습니다. 원본 게임 폴더에 해당 파일을 넣어 주세요.",Path.Combine(dir,name));
  var start=new ProcessStartInfo(editor){WorkingDirectory=dir,UseShellExecute=false};
  // The editor aborts with an empty MFC message unless GetDeviceCaps reports 16 bpp.
  // Apply the Windows shim only to this child; do not change desktop or registry settings.
  var layers=new List<string>();
  string inherited=start.EnvironmentVariables["__COMPAT_LAYER"]??"";
  foreach(string layer in inherited.Split(new[]{' ','\t'},StringSplitOptions.RemoveEmptyEntries))
   if(!layer.Equals("8BITCOLOR",StringComparison.OrdinalIgnoreCase)&&!layer.Equals("16BITCOLOR",StringComparison.OrdinalIgnoreCase)&&!layer.Equals("32BITCOLOR",StringComparison.OrdinalIgnoreCase))layers.Add(layer);
  layers.Add("16BITCOLOR");start.EnvironmentVariables["__COMPAT_LAYER"]=string.Join(" ",layers.ToArray());
  return start;
 }
}

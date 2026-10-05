using System;
using System.IO;
using System.Diagnostics;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Windows.Forms;
using System.Text;

internal static class EditorLaunch {
 internal static ProcessStartInfo Prepare(string game) {
  game=Path.GetFullPath(game);
  if(!File.Exists(game))throw new FileNotFoundException("게임 파일을 찾을 수 없습니다.",game);
  string dir=Path.GetDirectoryName(game),editor=Path.Combine(dir,"3kd2Edit.exe");
  foreach(string name in new[]{"3kd2Edit.exe","3kd2edit.DBX","RES.PAK","PALETTE.PAK"})
   if(!File.Exists(Path.Combine(dir,name)))throw new FileNotFoundException("에디터 실행에 필요한 "+name+" 파일이 없습니다. 원본 게임 폴더에 해당 파일을 넣어 주세요.",Path.Combine(dir,name));
  editor=Build(editor);
  var start=new ProcessStartInfo(editor){WorkingDirectory=dir,UseShellExecute=false,WindowStyle=ProcessWindowStyle.Maximized};
  // The editor aborts with an empty MFC message unless GetDeviceCaps reports 16 bpp.
  // Apply the Windows shim only to this child; do not change desktop or registry settings.
  var layers=new List<string>();
  string inherited=start.EnvironmentVariables["__COMPAT_LAYER"]??"";
  foreach(string layer in inherited.Split(new[]{' ','\t'},StringSplitOptions.RemoveEmptyEntries))
   if(!layer.Equals("8BITCOLOR",StringComparison.OrdinalIgnoreCase)&&!layer.Equals("16BITCOLOR",StringComparison.OrdinalIgnoreCase)&&!layer.Equals("32BITCOLOR",StringComparison.OrdinalIgnoreCase))layers.Add(layer);
  layers.Add("16BITCOLOR");start.EnvironmentVariables["__COMPAT_LAYER"]=string.Join(" ",layers.ToArray());
  return start;
 }
 static void Edit(byte[] data,int offset,byte[] expected,byte[] replacement) {
  for(int i=0;i<expected.Length;i++)if(data[offset+i]!=expected[i])throw new InvalidDataException("에디터 패치 위치 검증에 실패했습니다.");
  Buffer.BlockCopy(replacement,0,data,offset,replacement.Length);
 }
 internal static string Build(string original) {
  byte[] data=File.ReadAllBytes(original);
  // Resource/version metadata may differ while the executable code is identical.
  // Unknown code must run unmodified instead of blocking editor access.
  if(EditorUpgrade.IsSource(data))data=EditorUpgrade.Apply(data);
  if(!CompatibleLayout(data))return original;
  int width=800,height=600;
  foreach(var screen in Screen.AllScreens){width=Math.Max(width,screen.Bounds.Width+64);height=Math.Max(height,screen.Bounds.Height+64);}
  if(width>8192||height>8192)return original;
  // The game wrapper applies its stretching and primary-surface hooks to the
  // editor too. Resolve only this editor's DirectDraw import to Windows' x86
  // implementation, keeping the game's DLL and display settings untouched.
  string system=Environment.GetFolderPath(Environment.SpecialFolder.SystemX86);
  if(string.IsNullOrEmpty(system))system=Environment.SystemDirectory;
  string directDraw=Path.Combine(system,"ddraw.dll");
  if(!File.Exists(directDraw))directDraw=Path.Combine(Environment.SystemDirectory,"ddraw.dll");
  if(!File.Exists(directDraw))throw new FileNotFoundException("Windows DirectDraw 파일을 찾을 수 없습니다.",directDraw);
  byte[] directDrawName=Encoding.Default.GetBytes(directDraw+"\0");
  if(Encoding.Default.GetString(directDrawName)!=directDraw+"\0")throw new InvalidDataException("Windows DirectDraw 경로를 변환할 수 없습니다.");
  if(directDrawName.Length>256)throw new InvalidDataException("Windows DirectDraw 경로가 너무 깁니다.");
  Edit(data,0x276d00,new byte[directDrawName.Length],directDrawName);
  Edit(data,0x2c400c,BitConverter.GetBytes(0x597ccc),BitConverter.GetBytes(0x276d00));
  // Let MFC handle resize and min/max constraints; start the frame maximized.
  Edit(data,0x1bd9f,new byte[]{0x81,0x7d,0x0c,0x20,0x03},new byte[]{0xe9,0x4f,0,0,0});
  Edit(data,0x1c80f,new byte[]{0x75,0x20},new byte[]{0xeb,0x20});
  Edit(data,0x3f9d8,new byte[]{0x74,0x0f},new byte[]{0x90,0x90});
  // The windowed software renderer needs a backing surface larger than 800x600.
  foreach(int offset in new[]{0xa44dd,0xa450b,0xa4539})Edit(data,offset,BitConverter.GetBytes(800),BitConverter.GetBytes(width));
  foreach(int offset in new[]{0xa44e3,0xa4511,0xa453f})Edit(data,offset,BitConverter.GetBytes(600),BitConverter.GetBytes(height));
  // Expand the visible-object list: the original 1024-entry stack array overflows on large maps.
  Edit(data,0x2277a,BitConverter.GetBytes(0x104c),BitConverter.GetBytes(0x4004c));
  foreach(int offset in new[]{
   0x22785,0x2278b,0x22796,0x227a1,0x227a8,0x227af,0x227b9,0x227f6,0x22801,0x22807,
   0x2280f,0x22818,0x2281f,0x22825,0x22832,0x22838,0x22840,0x22849,0x22850,0x22856,
   0x22862,0x22869,0x22870,0x2288a,0x22891,0x228a7,0x228af,0x228b8,0x228df,0x228e7,
   0x228f0,0x228fc,0x22904,0x2290d,0x22913,0x2291c,0x22924,0x2292a,0x2293e,0x22944,
   0x2294b,0x22951,0x2295a,0x22960,0x2297e,0x22985,0x22995,0x2299e,0x229aa,0x229b1,
   0x229ba,0x229c6,0x229cd,0x229d9,0x229e7,0x229ee,0x229fa,0x22a08,0x22a0e,0x22a1c,
   0x22a28,0x22a31,0x22a37,0x22a3d,0x22a45,0x22a50,0x22a58,0x22a5f,0x22a6e,0x22a76,
   0x22a7d,0x22a8b,0x22a92,0x22a98,0x22a9f,0x22aaa,0x22ab1,0x22add,0x22ae8,0x22af0,
   0x22af7,0x22b06,0x22b0e,0x22b15,0x22b4e,0x22b56,0x22b5e,0x22b66,0x22b7b,0x22b83,
   0x22b8a,0x22b9d,0x22ba5,0x22bac
  }) {
   int displacement=BitConverter.ToInt32(data,offset);
   if(displacement> -0x1000||displacement< -0x104c)throw new InvalidDataException("에디터 지도 배열 검증 실패");
   Edit(data,offset,BitConverter.GetBytes(displacement),BitConverter.GetBytes(displacement-0x3f000));
  }
  // Size the split panes from the editor's own WM_SIZE coordinates (DPI-safe).
  byte[] layout={0x9c,0x60,0x8b,0x91,0x34,0x01,0,0,0x85,0xd2,0x74,0x17,0x8b,0x45,0x0c,0x2d,0x40,0x01,0,0,0x3d,0x3a,0x02,0,0,0x7d,0x05,0xb8,0x3a,0x02,0,0,0x89,0x42,0x04,0x61,0x9d,0xe9,0,0,0,0};
  Buffer.BlockCopy(BitConverter.GetBytes(0x64dfee-(0x676c40+layout.Length)),0,layout,38,4);
  Edit(data,0x276c40,new byte[layout.Length],layout);
  byte[] call={0xe8,0,0,0,0};Buffer.BlockCopy(BitConverter.GetBytes(0x676c40-0x41be07),0,call,1,4);
  Edit(data,0x1be02,new byte[]{0xe8,0xe7,0x21,0x23,0},call);
  string output=Path.Combine(Path.GetDirectoryName(original),"3kd2Edit-modern.exe");
  foreach(var process in Process.GetProcessesByName("3kd2Edit-modern"))using(process)
   if(!process.HasExited)throw new InvalidOperationException("호환 에디터가 실행 중입니다. 기존 에디터를 종료한 뒤 다시 실행하세요.");
  File.WriteAllBytes(output,data);return output;
 }
 internal static bool CompatibleLayout(byte[] data) {
  if(EditorUpgrade.IsSource(data))return true;
  try {
   if(data.Length<0x2c4000||BitConverter.ToUInt16(data,0)!=0x5a4d)return false;
   int pe=BitConverter.ToInt32(data,0x3c);
   if(pe<0||pe>data.Length-256||BitConverter.ToUInt32(data,pe)!=0x4550||BitConverter.ToUInt16(data,pe+4)!=0x14c)return false;
   int optional=pe+24;
   if(BitConverter.ToUInt16(data,optional)!=0x10b||BitConverter.ToUInt32(data,optional+28)!=0x400000)return false;
   int sections=optional+BitConverter.ToUInt16(data,pe+20);
   if(BitConverter.ToUInt16(data,pe+6)<4)return false;
   int[] rvas={0x1000,0x277000,0x29e000,0x596000},raw={0x1000,0x277000,0x29e000,0x2c4000};
   for(int i=0;i<4;i++)if(BitConverter.ToInt32(data,sections+i*40+12)!=rvas[i]||BitConverter.ToInt32(data,sections+i*40+20)!=raw[i])return false;
   using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(data,0x1000,0x2c3000)).Replace("-","")=="DEBACAD1D9EACDA7FF3F8784929868716A4D8DA4750B7D24F44CAFF38652E09F";
  }catch(ArgumentException){return false;}
 }
}

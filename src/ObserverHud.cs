using System;
using System.IO;
using System.Collections.Generic;
using System.Runtime.InteropServices;

// Only the private HUD1 presentation flag can be written by this controller.
internal sealed class ObserverHud {
 [DllImport("kernel32.dll")]static extern bool WriteProcessMemory(IntPtr process,IntPtr address,byte[] data,int size,out IntPtr done);
 readonly IntPtr process;readonly int flag;
 internal bool Hidden {get;private set;}
 internal ObserverHud(IntPtr handle,Dictionary<string,object> profile,Func<int,int,byte[]> read){
  process=handle;object value;if(!profile.TryGetValue("observer_hud_flag",out value))return;
  flag=Convert.ToInt32(value);byte[] magic=read(flag-4,4);
  if(magic==null||System.Text.Encoding.ASCII.GetString(magic)!="HUD1")throw new IOException("관전 HUD 표시 패치가 일치하지 않습니다.");
 }
 internal void Set(bool hidden){if(flag==0){if(hidden)throw new IOException("HUD 숨김을 지원하는 버전으로 게임을 다시 실행해 주세요.");return;}IntPtr done;if(!WriteProcessMemory(process,new IntPtr(flag),BitConverter.GetBytes(hidden?1:0),4,out done)||done.ToInt32()!=4)throw new IOException("관전 HUD 표시 설정 실패");Hidden=hidden;}
 internal void Reset(){try{Set(false);}catch(IOException){}}
}

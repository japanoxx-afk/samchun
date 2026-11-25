using System;
using System.IO;
using System.Text;
using System.Drawing;
using System.Diagnostics;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Web.Script.Serialization;
using System.Windows.Forms;

// 1.20g: 519CA4 checks initial slot kind 3; 519D5D stores it at +35.
// Initial spectators set +1685/+168D, but defeated players also set +1685.
// Therefore use the original kind, not the mutable defeated flag.
internal static class LiveObserverSnapshot {
 internal sealed class Snapshot {internal int Context,Generation;internal List<ObserverPlayerRow> Rows=new List<ObserverPlayerRow>();}
 static int Value(Func<int,int,byte[]> read,int address){byte[] b=read(address,4);if(b==null||b.Length!=4)throw new IOException("관전 상태 읽기 실패");return BitConverter.ToInt32(b,0);}
 internal static Snapshot Capture(Func<int,int,byte[]> read,int initial,int ending,int generation,int cleaned,Func<int,int> workerCount=null) {
  if(Value(read,initial)<4||Value(read,ending)!=0||Value(read,cleaned)!=0)return null;
  int gen=Value(read,generation),ctx=Value(read,0x837dcc);if(ctx<=0)return null;
  if(Value(read,ctx)!=2)return null;
  int count=Value(read,ctx+8),queues=Value(read,ctx+0x30),local=Value(read,ctx+0x58);
  if(count<1||count>9||queues<1||queues>9||local<=0)return null;
  int localSlot=Value(read,local+0x18);
  if(localSlot<0||localSlot>=count||Value(read,ctx+12+localSlot*4)!=local||Value(read,local+0x35)!=3)return null;
  var result=new Snapshot{Context=ctx,Generation=gen};
  for(int i=0;i<Math.Min(count,queues);i++) {
   if(Value(read,ctx+0x34+i*4)==0)continue;
   int player=Value(read,ctx+12+i*4);if(player<=0||Value(read,player+0x35)==3)continue;
   var row=ObserverPlayerRow.Read(read,player,i,null,workerCount);if(row!=null)result.Rows.Add(row);
  }
  // Discard a frame if cleanup or a new world began while the table was read.
  if(Value(read,0x837dcc)!=ctx||Value(read,generation)!=gen||Value(read,ending)!=0||Value(read,cleaned)!=0)return null;
  return result.Rows.Count==0?null:result;
 }
}

internal sealed class LiveObserverContext : ApplicationContext {
 [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access,bool inherit,int pid);
 [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h,IntPtr p,byte[] b,int n,out IntPtr done);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr window,out RECT rect);
 [DllImport("user32.dll")] static extern bool ClientToScreen(IntPtr window,ref POINT point);
 delegate IntPtr KeyHook(int code,IntPtr message,IntPtr data);
 [DllImport("user32.dll")] static extern IntPtr SetWindowsHookEx(int type,KeyHook hook,IntPtr module,uint thread);
 [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr hook);
 [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr hook,int code,IntPtr message,IntPtr data);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr GetModuleHandle(string name);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern uint GetPrivateProfileString(string section,string key,string fallback,StringBuilder value,uint size,string file);
 struct RECT {public int Left,Top,Right,Bottom;}
 struct POINT {public int X,Y;}
 readonly Process game;readonly IntPtr memory;readonly ResourceOverlay panel=new ResourceOverlay();readonly Timer timer=new Timer();
 readonly List<Font> ownedFonts=new List<Font>();
 readonly ObserverHud hud;
 readonly ObserverWorkerCounter workers=new ObserverWorkerCounter();
 readonly int initial,ending,generation,cleaned;readonly bool aspect;readonly float dpi;
 KeyHook keyboard;IntPtr keyboardHandle;
 bool show=true,iDown,uDown,hadObserver;int previousGeneration=-1,previousContext;
 byte[] Read(int address,int size){byte[] b=new byte[size];IntPtr done;return address>0&&ReadProcessMemory(memory,new IntPtr(address),b,size,out done)&&done.ToInt32()==size?b:null;}
 int U(int address){byte[] b=Read(address,4);return b==null?0:BitConverter.ToInt32(b,0);}
 public LiveObserverContext(int pid,string work) {
  game=Process.GetProcessById(pid);var json=new JavaScriptSerializer();var profile=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(work,"runtime.json")));
  string file=game.MainModule.FileName;using(var hash=SHA256.Create()){string actual=BitConverter.ToString(hash.ComputeHash(File.ReadAllBytes(file))).Replace("-","");if(!actual.Equals(Convert.ToString(profile["output_sha256"]),StringComparison.OrdinalIgnoreCase))throw new IOException("관전 실행 파일 불일치");}
  initial=Convert.ToInt32(profile["initial_save_header"]);ending=Convert.ToInt32(profile["end_transition_header"]);generation=Convert.ToInt32(profile["session_generation_address"]);cleaned=Convert.ToInt32(profile["session_cleanup_complete_address"]);
  // Participant state is read only; writes are restricted to the private HUD1 flag.
  memory=OpenProcess(0x1038,false,pid);if(memory==IntPtr.Zero)throw new IOException("관전 게임 읽기 연결 실패");
  hud=new ObserverHud(memory,profile,Read);
  using(var g=Graphics.FromHwnd(IntPtr.Zero))dpi=g.DpiX/96;
  var value=new StringBuilder(32);string ini=Path.Combine(Path.GetDirectoryName(file),"ddraw.ini");GetPrivateProfileString("ddraw","maintas","false",value,32,ini);string fallback=value.ToString();value.Length=0;GetPrivateProfileString(Path.GetFileNameWithoutExtension(file),"maintas",fallback,value,32,ini);aspect=value.ToString().Equals("true",StringComparison.OrdinalIgnoreCase);
  panel.LiveMode=true;panel.Text="실시간 관전 자원 현황";var initialFont=new Font("맑은 고딕",9);ownedFonts.Add(initialFont);panel.Font=initialFont;
  keyboard=Keyboard;   // 1.3.62: the global keyboard hook exists only while observing (see SetHook)
  timer.Interval=150;timer.Tick+=delegate{RefreshPanel();};timer.Start();
  File.WriteAllText(Path.Combine(work,"live-observer-ready"),"participant-read-only; private-HUD-flag");
 }
 void RefreshPanel() {
  game.Refresh();if(game.HasExited){ExitThread();return;}
  try {
   var state=LiveObserverSnapshot.Capture(Read,initial,ending,generation,cleaned,p=>workers.Count(Read,p));
   IntPtr window=game.MainWindowHandle;RECT r;POINT origin=new POINT();
   if(state==null||window==IntPtr.Zero||!GetClientRect(window,out r)||r.Right<100||r.Bottom<100||!ClientToScreen(window,ref origin)){panel.Hide();if(hadObserver){hud.Reset();hadObserver=false;}SetHook(false);return;}
   hadObserver=true;SetHook(true);
   if(previousGeneration!=state.Generation||previousContext!=state.Context){show=true;hud.Reset();workers.Clear();previousGeneration=state.Generation;previousContext=state.Context;}
   bool active=GetForegroundWindow()==window;
   if(!active||!show||hud.Hidden){panel.Hide();return;}
   int logicalHeight=72+state.Rows.Count*26;
   float scale=Math.Min(dpi,Math.Min(Math.Max(1,r.Right-24)/(float)ResourceOverlay.TableWidth,Math.Max(1,r.Bottom-24)/(float)logicalHeight));
   if(Math.Abs(panel.UiScale-scale)>0.001f){panel.UiScale=scale;float points=9*scale/dpi;if(Math.Abs(panel.Font.SizeInPoints-points)>0.001f){var next=new Font("맑은 고딕",points);ownedFonts.Add(next);panel.Font=next;}}
   panel.ClientSize=new Size((int)(ResourceOverlay.TableWidth*scale),(int)(logicalHeight*scale));panel.Location=new Point(origin.X+r.Right-panel.Width-12,origin.Y+12);
   panel.PlayerRows=state.Rows;panel.ResourceText="";panel.HasGameCursor=true;panel.ScreenCursor=NativeCursor(window,r,origin);
   if(!panel.Visible)panel.Show();panel.Invalidate();
  }catch(IOException){panel.Hide();}
 }
 IntPtr Keyboard(int code,IntPtr message,IntPtr data){
  if(code>=0){int key=Marshal.ReadInt32(data),m=message.ToInt32();bool down=m==0x100||m==0x104;
   if(key==73||key==85){bool held=key==73?iDown:uDown;if(!down){if(key==73)iDown=false;else uDown=false;}
    if(hadObserver&&GetForegroundWindow()==game.MainWindowHandle){
     if(down&&!held){if(key==73){iDown=true;show=!show;}else{uDown=true;try{hud.Set(!hud.Hidden);}catch(IOException){panel.Hide();}}}
     return new IntPtr(1);
    }
   }
  }return CallNextHookEx(keyboardHandle,code,message,data);
 }
 Point NativeCursor(IntPtr window,RECT r,POINT origin){byte[] b=Read(0x837f20,4);int w=U(0xb1f95c),h=U(0xb1f960);if(b==null||w<320||w>8192||h<200||h>8192)return Cursor.Position;int x=BitConverter.ToInt16(b,0),y=BitConverter.ToInt16(b,2);if(x<0||y<0||x>=w||y>=h)return Cursor.Position;double sx=(double)r.Right/w,sy=(double)r.Bottom/h;if(aspect)sx=sy=Math.Min(sx,sy);return new Point(origin.X+(int)((r.Right-w*sx)/2+x*sx),origin.Y+(int)((r.Bottom-h*sy)/2+y*sy));}
 // Players never get a global low-level keyboard hook: it delays every key press while
 // this process is busy and is the only place keys are swallowed (I/U, observers only).
 void SetHook(bool on){if(on&&keyboardHandle==IntPtr.Zero)keyboardHandle=SetWindowsHookEx(13,keyboard,GetModuleHandle(null),0);else if(!on&&keyboardHandle!=IntPtr.Zero){UnhookWindowsHookEx(keyboardHandle);keyboardHandle=IntPtr.Zero;iDown=uDown=false;}}
 protected override void ExitThreadCore(){timer.Dispose();if(keyboardHandle!=IntPtr.Zero)UnhookWindowsHookEx(keyboardHandle);hud.Reset();panel.Close();foreach(var font in ownedFonts)font.Dispose();ownedFonts.Clear();if(memory!=IntPtr.Zero)CloseHandle(memory);game.Dispose();base.ExitThreadCore();}
}

using System;
using System.IO;
using System.Text;
using System.Drawing;
using System.Diagnostics;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using System.Windows.Forms;

// A playback-only panel. Reads presentation data; writes only pacing and pause.
class ObserverForm : Form {
 protected override bool ShowWithoutActivation {get{return true;}}
 protected override CreateParams CreateParams {get{var p=base.CreateParams;p.ExStyle|=0x08000000;return p;}}
 protected override void WndProc(ref Message m){if(m.Msg==0x21){m.Result=new IntPtr(3);return;}base.WndProc(ref m);}
}
// Layered + transparent makes hit testing pass to the game across processes.
// Paint the cursor last because this legacy game draws its cursor into its surface.
class ResourceOverlay : ObserverForm {
 public string ResourceText="";public Point ScreenCursor;public bool HasGameCursor;public int Rate=1;public float UiScale=1;public bool LiveMode;public const int TableWidth=650;public List<ObserverPlayerRow> PlayerRows=new List<ObserverPlayerRow>();
 public Rectangle SpeedRect(int i){return new Rectangle((int)((12+i*80)*UiScale),(int)(34*UiScale),(int)(72*UiScale),(int)(26*UiScale));}
 Timer cursorTimer=new Timer();
 protected override CreateParams CreateParams {get{var p=base.CreateParams;p.ExStyle|=0x20|0x80000;return p;}}
 public ResourceOverlay(){FormBorderStyle=FormBorderStyle.None;ShowInTaskbar=false;TopMost=true;BackColor=Color.FromArgb(25,28,34);ForeColor=Color.White;Opacity=0.94;DoubleBuffered=true;cursorTimer.Interval=30;cursorTimer.Tick+=delegate{if(Visible)Invalidate();};cursorTimer.Start();}
 protected override void OnPaint(PaintEventArgs e){
  base.OnPaint(e);using(var brush=new SolidBrush(ForeColor)){
   string title=LiveMode?"실시간 관전 · I 현황 · U HUD 숨김":"리플레이 · "+Rate+"배속 · Esc 종료 · I 현황 · U HUD 숨김";
   e.Graphics.DrawString(title,Font,brush,10*UiScale,7*UiScale);
   int[] rates={1,2,4};if(!LiveMode)for(int i=0;i<3;i++){Rectangle r=SpeedRect(i);using(var fill=new SolidBrush(rates[i]==Rate?Color.FromArgb(65,90,110):Color.FromArgb(55,60,70)))e.Graphics.FillRectangle(fill,r);e.Graphics.DrawRectangle(Pens.LightGray,r);e.Graphics.DrawString(rates[i]+"배속",Font,brush,r.X+15*UiScale,r.Y+5*UiScale);}
   float y=LiveMode?35:73;
   if(!String.IsNullOrEmpty(ResourceText)){e.Graphics.DrawString(ResourceText.TrimEnd(),Font,brush,10*UiScale,y*UiScale);y+=25;}
   int[] starts={10,190,286,370,455,565};int[] widths={172,86,74,74,102,72};string[] headings={"플레이어 ID","진영","기","오어","인구","일꾼"};
   for(int i=0;i<6;i++)Cell(e.Graphics,headings[i],brush,starts[i],y,widths[i],i>=2);
   y+=26;
   foreach(var row in PlayerRows){
    using(var team=new SolidBrush(row.TeamColor)){e.Graphics.FillRectangle(team,10*UiScale,(y+5)*UiScale,4*UiScale,13*UiScale);Cell(e.Graphics,row.Name,team,20,y,162,false);}
    using(var team=new SolidBrush(row.TeamColor)){e.Graphics.FillRectangle(team,190*UiScale,(y+6)*UiScale,8*UiScale,8*UiScale);Cell(e.Graphics,row.Faction,team,203,y,73,false);}
    Cell(e.Graphics,row.Ki.ToString("N0"),brush,starts[2],y,widths[2],true);
    Cell(e.Graphics,row.Ore.ToString("N0"),brush,starts[3],y,widths[3],true);
    Cell(e.Graphics,row.PopulationUsed+" / "+row.PopulationCap,brush,starts[4],y,widths[4],true);
    Cell(e.Graphics,row.Workers<0?"—":row.Workers.ToString("N0"),brush,starts[5],y,widths[5],true);y+=26;
   }
  }
  Point cursor=PointToClient(HasGameCursor?ScreenCursor:Cursor.Position);if(ClientRectangle.Contains(cursor))Cursors.Arrow.Draw(e.Graphics,new Rectangle(cursor,Cursors.Arrow.Size));
 }
 void Cell(Graphics g,string value,Brush brush,float x,float y,float width,bool right){using(var format=new StringFormat{Alignment=right?StringAlignment.Far:StringAlignment.Near,Trimming=StringTrimming.EllipsisCharacter,FormatFlags=StringFormatFlags.NoWrap})g.DrawString(value??"",Font,brush,new RectangleF(x*UiScale,y*UiScale,width*UiScale,25*UiScale),format);}
 protected override void OnFormClosed(FormClosedEventArgs e){cursorTimer.Dispose();base.OnFormClosed(e);}
}
class ReplayControls : ObserverForm {
 readonly ObserverWorkerCounter workers=new ObserverWorkerCounter();
 [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access,bool inherit,int pid);
 [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h,IntPtr p,byte[] b,int n,out IntPtr done);
 [DllImport("kernel32.dll")] static extern bool WriteProcessMemory(IntPtr h,IntPtr p,byte[] b,int n,out IntPtr done);
 [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr h,uint code);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 delegate IntPtr Hook(int code,IntPtr message,IntPtr data);
 [DllImport("user32.dll")] static extern IntPtr SetWindowsHookEx(int type,Hook hook,IntPtr module,uint thread);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr GetModuleHandle(string name);
 [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr hook);
 [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr h,int code,IntPtr w,IntPtr l);
 [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern uint GetPrivateProfileString(string section,string key,string fallback,StringBuilder value,uint size,string file);
 [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr window);
 [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr window,out RECT rect);
 [DllImport("user32.dll")] static extern bool ClientToScreen(IntPtr window,ref POINT point);
 struct RECT {public int Left,Top,Right,Bottom;}
 struct POINT {public int X,Y;}
 IntPtr memory,hookHandle,mouseHandle; Hook hook,mouseHook; bool mouseCaptured,maintainAspect; int currentSpeed=1; Process game; string work; int speedAddress,readyAddress,endAddress,nativeMouseCounter,nativeMousePoint,lastNativeClick;
 Action<bool> pendingAnswer;bool asking,finishing,resourcesVisible=true; uint previousPause; int lastKey;
 ResourceOverlay resourceOverlay=new ResourceOverlay();ObserverHud hud;float displayDpi=1;List<Font> displayFonts=new List<Font>();
 Timer timer=new Timer(); int[] slots;int firstTick,lastTick,tickRate=30;Dictionary<int,string> names=new Dictionary<int,string>();
 JavaScriptSerializer json=new JavaScriptSerializer();
 static int Number(Dictionary<string,object> d,string key){return Convert.ToInt32(d[key]);}
 byte[] Read(int p,int n) {byte[] b=new byte[n];IntPtr count;if(p==0||!ReadProcessMemory(memory,new IntPtr(p),b,n,out count)||count.ToInt32()!=n)return null;return b;}
 int U(int p){var b=Read(p,4);return b==null?0:BitConverter.ToInt32(b,0);}
 void Write(int p,int value){IntPtr done;if(!WriteProcessMemory(memory,new IntPtr(p),BitConverter.GetBytes(value),4,out done)||done.ToInt32()!=4)throw new IOException("관전 제어 메모리 쓰기 실패");}
 public ReplayControls(string[] args) {
  game=Process.GetProcessById(int.Parse(args[0]));work=args[1];var profile=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(work,"runtime.json")));
  speedAddress=Number(profile,"observer_speed_address");readyAddress=Number(profile,"autoload_status_address");endAddress=Number(profile,"playback_end_flag");
  nativeMouseCounter=Number(profile,"observer_native_mouse_counter");nativeMousePoint=Number(profile,"observer_native_mouse_point");
  memory=OpenProcess(0x1039,false,game.Id);if(memory==IntPtr.Zero)throw new IOException("관전 게임 연결 실패");hud=new ObserverHud(memory,profile,Read);
  var settings=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(work,"controls.json")));var list=new List<int>();foreach(object x in (System.Collections.IEnumerable)settings["slots"])list.Add(Convert.ToInt32(x));slots=list.ToArray();firstTick=Number(settings,"first_tick");lastTick=Number(settings,"last_tick");tickRate=Number(settings,"tick_rate");if(settings.ContainsKey("participants"))foreach(object x in (System.Collections.IEnumerable)settings["participants"]){var row=(Dictionary<string,object>)x;names[Number(row,"slot")]=Convert.ToString(row["id"]);}
  var aspect=new StringBuilder(32);string ini=Path.Combine(Path.GetDirectoryName(game.MainModule.FileName),"ddraw.ini");GetPrivateProfileString("ddraw","maintas","false",aspect,32,ini);string fallback=aspect.ToString();aspect.Length=0;GetPrivateProfileString("3kd2-playback","maintas",fallback,aspect,32,ini);maintainAspect=aspect.ToString().Equals("true",StringComparison.OrdinalIgnoreCase);
  Text="리플레이 관전";FormBorderStyle=FormBorderStyle.None;ShowInTaskbar=false;TopMost=true;BackColor=Color.FromArgb(25,28,34);ForeColor=Color.White;Font=new Font("맑은 고딕",9);using(var g=Graphics.FromHwnd(IntPtr.Zero))resourceOverlay.UiScale=g.DpiX/96;displayDpi=resourceOverlay.UiScale;ClientSize=new Size((int)(ResourceOverlay.TableWidth*resourceOverlay.UiScale),1);resourceOverlay.ClientSize=new Size(Width,(int)((slots.Length*23+133)*resourceOverlay.UiScale));resourceOverlay.Font=Font;Shown+=delegate{resourceOverlay.Show(this);};
  Opacity=0;DoubleBuffered=true;
  mouseHook=Mouse;mouseHandle=SetWindowsHookEx(14,mouseHook,GetModuleHandle(null),0);if(mouseHandle==IntPtr.Zero)throw new IOException("리플레이 마우스 제어 연결 실패");
  hook=Keyboard;hookHandle=SetWindowsHookEx(13,hook,GetModuleHandle(null),0);if(hookHandle==IntPtr.Zero)throw new IOException("리플레이 Esc 제어 연결 실패");
  timer.Interval=30;timer.Tick+=delegate{UpdatePanel();};timer.Start();
  File.WriteAllText(Path.Combine(work,"controls-ready"),"1");
 }
 protected override CreateParams CreateParams {get{var p=base.CreateParams;p.ExStyle|=0x20|0x80000;return p;}}
 Rectangle SpeedButton(int i){return resourceOverlay.SpeedRect(i);}
 // 517B17 stores native mouse-event x/y at 837F20/22 before world conversion.
 // DirectInput keeps this software cursor separate from the Windows cursor.
 Point GameCursor(){return NativeScreenPoint(Read(0x837f20,4));}
 Point NativeScreenPoint(byte[] b){int width=U(0xb1f95c),height=U(0xb1f960);RECT r;POINT origin=new POINT();IntPtr window=game.MainWindowHandle;if(b==null||width<320||width>8192||height<200||height>8192||window==IntPtr.Zero||!GetClientRect(window,out r)||!ClientToScreen(window,ref origin))return Cursor.Position;int x=BitConverter.ToInt16(b,0),y=BitConverter.ToInt16(b,2);if(x<0||y<0||x>=width||y>=height)return Cursor.Position;double sx=(double)r.Right/width,sy=(double)r.Bottom/height;if(maintainAspect)sx=sy=Math.Min(sx,sy);return new Point(origin.X+(int)((r.Right-width*sx)/2+x*sx),origin.Y+(int)((r.Bottom-height*sy)/2+y*sy));}
 IntPtr Mouse(int code,IntPtr message,IntPtr data){
  int m=message.ToInt32();if(code>=0){if(m==0x202&&mouseCaptured){mouseCaptured=false;return new IntPtr(1);}if(m==0x201&&Visible&&resourcesVisible&&!asking&&!finishing&&GetForegroundWindow()==game.MainWindowHandle){Point p=resourceOverlay.PointToClient(GameCursor());for(int i=0;i<3;i++)if(SpeedButton(i).Contains(p)){int rate=new int[]{1,2,4}[i];mouseCaptured=true;BeginInvoke((Action)delegate{Write(speedAddress,rate);currentSpeed=rate;Invalidate();});return new IntPtr(1);}}}return CallNextHookEx(mouseHandle,code,message,data);
 }
 IntPtr Keyboard(int code,IntPtr message,IntPtr data) {
  if(code>=0 && GetForegroundWindow()==game.MainWindowHandle) {
   int key=Marshal.ReadInt32(data),m=message.ToInt32();bool down=m==0x100||m==0x104;
   if(pendingAnswer!=null && (key==27||key==13||key==89||key==78)) {
    if(down&&lastKey!=key){lastKey=key;bool yes=finishing||key==89;BeginInvoke((Action)delegate{if(pendingAnswer!=null)pendingAnswer(yes);});}
    if(!down)lastKey=0;return new IntPtr(1);
   }
   if(!finishing && (key==27||key==73||key==85)) {
    if(down&&lastKey!=key){lastKey=key;if(key==27)BeginInvoke((Action)AskStop);else BeginInvoke((Action)delegate{if(key==85){if(U(readyAddress)==2&&U(endAddress)==0)hud.Set(!hud.Hidden);}else resourcesVisible=!resourcesVisible;ApplyVisibility();});}
    if(!down)lastKey=0;return new IntPtr(1);
   }
  }
  return CallNextHookEx(hookHandle,code,message,data);
 }
 void AskStop() {
  if(asking||finishing||U(readyAddress)!=2||U(endAddress)!=0)return;
  asking=true;previousPause=(uint)U(0x837f24);Write(0x837f24,1);
  Notice("리플레이 구동을 종료하시겠습니까?\nY: 예 · N/Enter/Esc: 아니요",true,delegate(bool yes){
   if(yes){File.WriteAllText(Path.Combine(work,"user-stop.json"),json.Serialize(new {pid=game.Id,result="user-stopped",tick=U(0x8a1238)}));finishing=true;TerminateProcess(memory,0);Close();}
   else {Write(0x837f24,(int)previousPause);asking=false;lastKey=0;}
  });
 }
 void UpdatePanel() {
  string resultPath=Path.Combine(work,"control-result.json");
  if(File.Exists(resultPath)&&!finishing){finishing=true;timer.Stop();Opacity=0.94;Notice("리플레이가 종료되었습니다.\nEnter 키 또는 확인 버튼으로 닫습니다.",false,delegate(bool ok){TerminateProcess(memory,0);Close();});return;}
  game.Refresh();if(game.HasExited){if(!File.Exists(Path.Combine(work,"user-stop.json")))Close();return;}
  IntPtr window=game.MainWindowHandle;RECT rect;POINT p=new POINT();if(window==IntPtr.Zero||!GetClientRect(window,out rect))return;ClientToScreen(window,ref p);float scale=Math.Min(displayDpi,Math.Min(Math.Max(1,rect.Right-24)/(float)ResourceOverlay.TableWidth,Math.Max(1,rect.Bottom-24)/(float)(136+slots.Length*26)));if(Math.Abs(scale-resourceOverlay.UiScale)>0.001f){resourceOverlay.UiScale=scale;float points=9*scale/displayDpi;if(Math.Abs(resourceOverlay.Font.SizeInPoints-points)>0.001f){var font=new Font("맑은 고딕",points);displayFonts.Add(font);resourceOverlay.Font=font;}}Width=(int)(ResourceOverlay.TableWidth*scale);resourceOverlay.Width=Width;Location=new Point(p.X+Math.Max(0,rect.Right-Width-12),p.Y+12);
  resourceOverlay.Location=Location;resourceOverlay.ScreenCursor=GameCursor();resourceOverlay.HasGameCursor=true;ApplyVisibility();int click=U(nativeMouseCounter);if(click!=lastNativeClick){lastNativeClick=click;if(Visible&&resourcesVisible&&!asking&&!finishing){Point hit=resourceOverlay.PointToClient(NativeScreenPoint(Read(nativeMousePoint,4)));for(int i=0;i<3;i++)if(SpeedButton(i).Contains(hit)){int rate=new int[]{1,2,4}[i];Write(speedAddress,rate);currentSpeed=rate;Invalidate();}}}if(U(readyAddress)!=2)return;
  int ctx=U(0x837dcc);if(ctx==0)return;var rows=new List<ObserverPlayerRow>();
  try{foreach(int slot in slots){if(slot<0||slot>=Math.Min(9,U(ctx+8)))continue;int player=U(ctx+12+slot*4);if(player==0)continue;string name;names.TryGetValue(slot,out name);var row=ObserverPlayerRow.Read(Read,player,slot,name,address=>workers.Count(Read,address));if(row!=null)rows.Add(row);}}catch(IOException){return;}
  if(U(0x837dcc)!=ctx)return;
  int elapsed=Math.Max(0,Math.Min(U(0x8a1238),lastTick)-firstTick)/tickRate,duration=Math.Max(0,lastTick-firstTick)/tickRate;
  resourceOverlay.Rate=currentSpeed;resourceOverlay.ResourceText="경과 "+Clock(elapsed)+" / "+Clock(duration);resourceOverlay.PlayerRows=rows;
  resourceOverlay.Height=(int)((136+rows.Count*26)*resourceOverlay.UiScale);resourceOverlay.Invalidate();Invalidate();
 }
 static string Clock(int seconds){return seconds>=3600?String.Format("{0:00}:{1:00}:{2:00}",seconds/3600,seconds/60%60,seconds%60):String.Format("{0:00}:{1:00}",seconds/60,seconds%60);}
 void ApplyVisibility(){bool active=GetForegroundWindow()==game.MainWindowHandle||GetForegroundWindow()==Handle||asking;bool show=active&&resourcesVisible&&!hud.Hidden;if(show){if(!Visible)Show();if(!resourceOverlay.Visible)resourceOverlay.Show(this);}else{resourceOverlay.Hide();Hide();}}

 void Notice(string text,bool question,Action<bool> answer){
  var dialog=new ObserverForm{Text=question?"리플레이 종료":"리플레이",FormBorderStyle=FormBorderStyle.FixedDialog,MinimizeBox=false,MaximizeBox=false,ShowInTaskbar=true,TopMost=true,StartPosition=FormStartPosition.Manual,ClientSize=new Size(360,140),Font=Font};
  RECT rect;POINT point=new POINT();GetClientRect(game.MainWindowHandle,out rect);ClientToScreen(game.MainWindowHandle,ref point);dialog.Location=new Point(point.X+(rect.Right-360)/2,point.Y+(rect.Bottom-140)/2);
  dialog.Controls.Add(new Label{Text=text,AutoSize=false,Location=new Point(18,24),Size=new Size(330,45)});
  bool answered=false;Action<bool> done=delegate(bool yes){if(answered)return;answered=true;dialog.Close();answer(yes);};
  var yesButton=new Button{Text=question?"예":"확인",Location=new Point(question?166:256,95),Size=new Size(85,28)};yesButton.Click+=delegate{done(true);};dialog.Controls.Add(yesButton);
  if(question){var noButton=new Button{Text="아니요",Location=new Point(256,95),Size=new Size(85,28)};noButton.Click+=delegate{done(false);};dialog.Controls.Add(noButton);}
  pendingAnswer=done;dialog.FormClosed+=delegate{pendingAnswer=null;if(!answered){answered=true;answer(!question);}};dialog.Show(this);
 }
 protected override void OnFormClosed(FormClosedEventArgs e){timer.Stop();if(mouseHandle!=IntPtr.Zero)UnhookWindowsHookEx(mouseHandle);hud.Reset();resourceOverlay.Close();foreach(var font in displayFonts)font.Dispose();displayFonts.Clear();if(hookHandle!=IntPtr.Zero)UnhookWindowsHookEx(hookHandle);if(memory!=IntPtr.Zero)CloseHandle(memory);base.OnFormClosed(e);}
 static void LogFailure(string[] args,Exception error){bool live=args.Length==3&&args[0]=="--live";string work=live?args[2]:(args.Length>1?args[1]:null);if(work!=null)try{File.WriteAllText(Path.Combine(work,live?"live-observer-error.log":"controls-error.log"),DateTime.UtcNow.ToString("o")+Environment.NewLine+(error==null?"Unknown UI exception":error.ToString()));}catch(IOException){} }
 [STAThread] static void Main(string[] args){SetProcessDPIAware();Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);Application.ThreadException+=(s,e)=>{LogFailure(args,e.Exception);Application.Exit();};AppDomain.CurrentDomain.UnhandledException+=(s,e)=>LogFailure(args,e.ExceptionObject as Exception);Application.EnableVisualStyles();try{if(args.Length==3&&args[0]=="--live")Application.Run(new LiveObserverContext(int.Parse(args[1]),args[2]));else Application.Run(new ReplayControls(args));}catch(Exception e){LogFailure(args,e);}}
}




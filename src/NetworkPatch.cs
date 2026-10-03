using System;
using System.IO;
using System.Text;
using System.Net;
using System.Net.Sockets;

// Route the Internet menu into the game's existing TCP/IP host/join flow.
// No central authentication server or new gameplay protocol is involved.
static class NetworkPatch {
 static void Put(byte[] b,int o,int value){Array.Copy(BitConverter.GetBytes(value),0,b,o,4);}
 static void Store(BinaryWriter w,int address,int value){w.Write((byte)0xc7);w.Write((byte)0x05);w.Write(address);w.Write(value);}
 internal static void Validate(bool host,string name,string ip) {
  if(string.IsNullOrWhiteSpace(name)||name.Length>15)throw new ArgumentException("플레이어 이름은 영문/숫자 1~15자로 입력하세요.");
  foreach(char c in name)if(!(c>='a'&&c<='z'||c>='A'&&c<='Z'||c>='0'&&c<='9'||c=='_'||c=='-'))throw new ArgumentException("플레이어 이름에 영문, 숫자, _, -만 사용할 수 있습니다.");
  IPAddress parsed;if(!host&&(!IPAddress.TryParse(ip,out parsed)||parsed.AddressFamily!=AddressFamily.InterNetwork||parsed.Equals(IPAddress.Any)||parsed.Equals(IPAddress.Broadcast)))throw new ArgumentException("A의 IPv4 주소를 입력하세요.");
 }
 internal static void Apply(string file,bool host,string name,string ip) {
  Validate(host,name,ip);byte[] b=File.ReadAllBytes(file);int pe=BitConverter.ToInt32(b,60),opt=pe+24;
  int count=BitConverter.ToUInt16(b,pe+6),section=opt+BitConverter.ToUInt16(b,pe+20)+(count-1)*40;
  if(Encoding.ASCII.GetString(b,section,6)!=".rally"||BitConverter.ToInt32(b,section+12)!=0x780000||BitConverter.ToInt32(b,section+8)>0x1400)throw new InvalidDataException("네트워크 패치 섹션 불일치");
  int raw=BitConverter.ToInt32(b,section+20);byte[] expected={0xe8,0xd2,0x5c,0xff,0xff};
  for(int i=0;i<5;i++)if(b[0x44af9+i]!=expected[i])throw new InvalidDataException("Internet 메뉴 패치 대상 불일치");
  int oldSize=BitConverter.ToInt32(b,section+16);Array.Resize(ref b,raw+0x1600);
  using(var m=new MemoryStream())using(var w=new BinaryWriter(m)){
   Store(w,0x851818,0);Store(w,0x733d70,0);Store(w,0x733d74,0);Store(w,0x733d7c,0);
   Store(w,0x733d78,0);Store(w,0x733d80,0xb81540);Store(w,0x733d84,0xb81500);Store(w,0x733d8c,0);
   Store(w,0x6c7da0,host?0x27:0x58);Store(w,0x6c7da4,0);
   w.Write((byte)0xe9);w.Write(0x460e82-(0xb81480+(int)m.Position+4));Array.Copy(m.ToArray(),0,b,raw+0x1480,m.Length);
  }
  if(host)using(var m=new MemoryStream())using(var w=new BinaryWriter(m)){
   // The previous dialog has been destroyed before this constructor is called.
   w.Write((byte)0x68);w.Write(0xb81500);w.Write((byte)0xe8);w.Write(0x4d83f0-(0xb81400+(int)m.Position+4));
   w.Write(new byte[]{0x83,0xc4,4,0x85,0xc0,0x75,3,0x31,0xc0,0xc3});
   Store(w,0x850dc4,1);Store(w,0x848d15,0x3f4);
   w.Write((byte)0xe9);w.Write(0x4d2450-(0xb81400+(int)m.Position+4));Array.Copy(m.ToArray(),0,b,raw+0x1400,m.Length);
   int creator=0x2c78f4+0x27*12;if(BitConverter.ToInt32(b,creator)!=0x4d2450)throw new InvalidDataException("방 만들기 메뉴 불일치");Put(b,creator,0xb81400);
  }
  if(!host)using(var m=new MemoryStream())using(var w=new BinaryWriter(m)){
   // The command-line join dialogs normally terminate the entire game on Cancel.
   // Menu-driven joining returns to the main menu instead.
   foreach(int target in new[]{0x443b70,0x4e87b0}){w.Write((byte)0xe8);w.Write(target-(0xb81400+(int)m.Position+4));}
   Store(w,0x6c7da0,1);Store(w,0x6c7da4,0);w.Write((byte)0xb8);w.Write(1);w.Write((byte)0xc3);
   Array.Copy(m.ToArray(),0,b,raw+0x1400,m.Length);
   foreach(int offset in new[]{0xd678b,0xd6dc8}){
    if(b[offset]!=0xc7||b[offset+1]!=5||BitConverter.ToInt32(b,offset+2)!=0x733d64||BitConverter.ToInt32(b,offset+6)!=3)throw new InvalidDataException("접속 취소 분기 불일치");
    b[offset]=0xe9;Put(b,offset+1,0xb81400-(0x400000+offset+5));for(int i=5;i<10;i++)b[offset+i]=0x90;
   }
  }
  Array.Copy(Encoding.ASCII.GetBytes(name+"\0"),0,b,raw+0x1500,name.Length+1);Array.Copy(Encoding.ASCII.GetBytes(ip+"\0"),0,b,raw+0x1540,ip.Length+1);
  byte[] button={0x68,0x78,0x8b,0x6c,0};for(int i=0;i<5;i++)if(b[0x60a29+i]!=button[i])throw new InvalidDataException("Internet 버튼 분기 불일치");
  b[0x60a29]=0xe9;Put(b,0x60a2a,0xb81480-0x460a2e);
  Put(b,section+8,0x1600);Put(b,section+16,0x1600);Put(b,opt+4,BitConverter.ToInt32(b,opt+4)+0x1600-oldSize);
  File.WriteAllBytes(file,b);
 }
}

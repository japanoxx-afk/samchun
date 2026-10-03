using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
class VerifyEmbeddedServer {
 static string Hash(string p){using(var s=File.OpenRead(p))using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(s));}
 static void Main(string[] args){var a=Assembly.LoadFile(Path.GetFullPath(args[0]));var m=a.GetType("Launcher").GetMethod("InstallServer",BindingFlags.NonPublic|BindingFlags.Static);string p=(string)m.Invoke(null,null);if(Hash(p)!=Hash(args[1]))throw new Exception("Embedded server mismatch");if((string)m.Invoke(null,null)!=p)throw new Exception("Repeated extraction mismatch");Console.WriteLine("Embedded server extraction/hash and repeated installation passed");}
}

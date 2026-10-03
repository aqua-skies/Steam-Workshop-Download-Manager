using System;
using Swdm2.Core.Logging;

var p = new RegexRedactionPolicy();
var cases = new[]
{
    "password=P@ssw0rd-饥荒-Don't",
    "\"token\": \"abc.def.ghi\"",
    "code=987654",
    "密码: hunter2",
    "postcode=12345",
    "pwd=s3cr3t",
    "\"token\": 'single.quoted'"
};
foreach (var s in cases)
    Console.WriteLine("IN  [" + s + "]");
Console.WriteLine("---");
foreach (var s in cases)
    Console.WriteLine("OUT [" + p.Redact(s) + "]");
return 0;

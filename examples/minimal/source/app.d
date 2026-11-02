import std.stdio; import semver; void main() { assert(SemVer("1.2.3").isValid); writeln("locked DUB"); }
unittest { assert(SemVer("2.3.4").isValid); }

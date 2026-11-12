# SPDX-License-Identifier: MIT
{
  symlinkJoin,
  nativeDub,
  nativeDcd,
  ldc,
  nativeServeD,
  git,
  gcc,
}:
symlinkJoin {
  name = "dub-purifier-toolchain";
  paths = [
    nativeDub
    nativeDcd
    ldc
    nativeServeD
    git
    gcc
  ];
}

# SPDX-License-Identifier: MIT
{ ... }:
{
  overlay = final: prev: {
    dub-purifier = (prev.dub-purifier or { }) // {
      readLock = import ./read-lock.nix { lib = final; };
    };
  };
}

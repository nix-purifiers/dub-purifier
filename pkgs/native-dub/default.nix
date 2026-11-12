# SPDX-License-Identifier: MIT
{ dub }:
dub.overrideAttrs (old: {
  patches = (old.patches or [ ]) ++ [ ./dub.patch ];
})

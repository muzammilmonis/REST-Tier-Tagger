# REST API bridge

REST Tier Tagger keeps upstream TierTagger's version-specific rendering code and changes only the data provider.

## Primary endpoint

- `https://tiers.rest/api/player/{player}`

The bridge intentionally accepts several JSON shapes because the existing REST Tier Tags server plugin already treats the API as flexible. It recognizes common containers such as:

- `placements`
- `rankings`
- `ranks`
- `gamemodes`
- `modes`
- `tiers`
- `tierMap`

A placement can be a compact string such as `HT1`/`LT2`, or an object containing `tier`, `rank`, `value`, `tierName`, or `placement`.

## Canonical tier order

`HT1 > LT1 > HT2 > LT2 > HT3 > LT3 > HT4 > LT4 > HT5 > LT5`

The bridge converts these strings to TierTagger's native ranking object:

- high tier => `pos = 0`
- low tier => `pos = 1`
- tier number => `tier = 1..5`

## UUID handling

TierTagger render hooks naturally identify players by UUID. The bridge tries the UUID against `tiers.rest` first. If the REST endpoint is name-only, it resolves the premium profile name from Mojang's session server, caches it, and retries by name.

## Mode compatibility

REST canonical mode `netherop` is emitted with aliases `nethop` and `neth_pot` because older TierTagger branches used different keys.

Known REST modes included by default:

`vanilla, uhc, pot, netherop, smp, sword, axe, mace, modernmace, minecart, spearmace, spearelytra, spear, trident, crystal, bow, shield`

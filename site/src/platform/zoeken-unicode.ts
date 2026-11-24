// Tekens zoals Python 3.12 ze ziet (unicodedata 15.0), voor het zoeken in TypeScript (B80, PLAN #34.2bo stap 4). Node en
// de Worker kennen een nieuwere Unicode: een teken dat in 15.0 nog niet bestond, is voor Python geen letter, heeft geen
// kleine letter en verandert niet bij normaliseren; hier net zo. Daarnaast de tekens waarvan `str.casefold()` iets anders
// geeft dan `toLowerCase()` (ß, ﬁ, ᾀ, Cherokee), en twee tekens die sinds 15.0 een andere eigenschap kregen.
// Gemaakt uit `unicodedata` van Python 3.12 naast Node 22 (Unicode 17); `tests/test_platform_ts_zoeken.py` legt elk teken
// naast Python.

const TOEGEWEZEN = '\u{0}-\u{377}\u{37a}-\u{37f}\u{384}-\u{38a}\u{38c}\u{38e}-\u{3a1}\u{3a3}-\u{52f}\u{531}-\u{556}\u{559}-\u{58a}\u{58d}-\u{58f}\u{591}-\u{5c7}\u{5d0}-\u{5ea}\u{5ef}-\u{5f4}\u{600}-\u{70d}\u{70f}-\u{74a}\u{74d}-\u{7b1}\u{7c0}-\u{7fa}\u{7fd}-\u{82d}\u{830}-\u{83e}\u{840}-\u{85b}\u{85e}\u{860}-\u{86a}\u{870}-\u{88e}\u{890}-\u{891}\u{898}-\u{983}\u{985}-\u{98c}\u{98f}-\u{990}\u{993}-\u{9a8}\u{9aa}-\u{9b0}\u{9b2}\u{9b6}-\u{9b9}\u{9bc}-\u{9c4}\u{9c7}-\u{9c8}\u{9cb}-\u{9ce}\u{9d7}\u{9dc}-\u{9dd}\u{9df}-\u{9e3}\u{9e6}-\u{9fe}\u{a01}-\u{a03}\u{a05}-\u{a0a}\u{a0f}-\u{a10}\u{a13}-\u{a28}\u{a2a}-\u{a30}\u{a32}-\u{a33}\u{a35}-\u{a36}\u{a38}-\u{a39}\u{a3c}\u{a3e}-\u{a42}\u{a47}-\u{a48}\u{a4b}-\u{a4d}\u{a51}\u{a59}-\u{a5c}\u{a5e}\u{a66}-\u{a76}\u{a81}-\u{a83}\u{a85}-\u{a8d}\u{a8f}-\u{a91}\u{a93}-\u{aa8}\u{aaa}-\u{ab0}\u{ab2}-\u{ab3}\u{ab5}-\u{ab9}\u{abc}-\u{ac5}\u{ac7}-\u{ac9}\u{acb}-\u{acd}\u{ad0}\u{ae0}-\u{ae3}\u{ae6}-\u{af1}\u{af9}-\u{aff}\u{b01}-\u{b03}\u{b05}-\u{b0c}\u{b0f}-\u{b10}\u{b13}-\u{b28}\u{b2a}-\u{b30}\u{b32}-\u{b33}\u{b35}-\u{b39}\u{b3c}-\u{b44}\u{b47}-\u{b48}\u{b4b}-\u{b4d}\u{b55}-\u{b57}\u{b5c}-\u{b5d}\u{b5f}-\u{b63}\u{b66}-\u{b77}\u{b82}-\u{b83}\u{b85}-\u{b8a}\u{b8e}-\u{b90}\u{b92}-\u{b95}\u{b99}-\u{b9a}\u{b9c}\u{b9e}-\u{b9f}\u{ba3}-\u{ba4}\u{ba8}-\u{baa}\u{bae}-\u{bb9}\u{bbe}-\u{bc2}\u{bc6}-\u{bc8}\u{bca}-\u{bcd}\u{bd0}\u{bd7}\u{be6}-\u{bfa}\u{c00}-\u{c0c}\u{c0e}-\u{c10}\u{c12}-\u{c28}\u{c2a}-\u{c39}\u{c3c}-\u{c44}\u{c46}-\u{c48}\u{c4a}-\u{c4d}\u{c55}-\u{c56}\u{c58}-\u{c5a}\u{c5d}\u{c60}-\u{c63}\u{c66}-\u{c6f}\u{c77}-\u{c8c}\u{c8e}-\u{c90}\u{c92}-\u{ca8}\u{caa}-\u{cb3}\u{cb5}-\u{cb9}\u{cbc}-\u{cc4}\u{cc6}-\u{cc8}\u{cca}-\u{ccd}\u{cd5}-\u{cd6}\u{cdd}-\u{cde}\u{ce0}-\u{ce3}\u{ce6}-\u{cef}\u{cf1}-\u{cf3}\u{d00}-\u{d0c}\u{d0e}-\u{d10}\u{d12}-\u{d44}\u{d46}-\u{d48}\u{d4a}-\u{d4f}\u{d54}-\u{d63}\u{d66}-\u{d7f}\u{d81}-\u{d83}\u{d85}-\u{d96}\u{d9a}-\u{db1}\u{db3}-\u{dbb}\u{dbd}\u{dc0}-\u{dc6}\u{dca}\u{dcf}-\u{dd4}\u{dd6}\u{dd8}-\u{ddf}\u{de6}-\u{def}\u{df2}-\u{df4}\u{e01}-\u{e3a}\u{e3f}-\u{e5b}\u{e81}-\u{e82}\u{e84}\u{e86}-\u{e8a}\u{e8c}-\u{ea3}\u{ea5}\u{ea7}-\u{ebd}\u{ec0}-\u{ec4}\u{ec6}\u{ec8}-\u{ece}\u{ed0}-\u{ed9}\u{edc}-\u{edf}\u{f00}-\u{f47}\u{f49}-\u{f6c}\u{f71}-\u{f97}\u{f99}-\u{fbc}\u{fbe}-\u{fcc}\u{fce}-\u{fda}\u{1000}-\u{10c5}\u{10c7}\u{10cd}\u{10d0}-\u{1248}\u{124a}-\u{124d}\u{1250}-\u{1256}\u{1258}\u{125a}-\u{125d}\u{1260}-\u{1288}\u{128a}-\u{128d}\u{1290}-\u{12b0}\u{12b2}-\u{12b5}\u{12b8}-\u{12be}\u{12c0}\u{12c2}-\u{12c5}\u{12c8}-\u{12d6}\u{12d8}-\u{1310}\u{1312}-\u{1315}\u{1318}-\u{135a}\u{135d}-\u{137c}\u{1380}-\u{1399}\u{13a0}-\u{13f5}\u{13f8}-\u{13fd}\u{1400}-\u{169c}\u{16a0}-\u{16f8}\u{1700}-\u{1715}\u{171f}-\u{1736}\u{1740}-\u{1753}\u{1760}-\u{176c}\u{176e}-\u{1770}\u{1772}-\u{1773}\u{1780}-\u{17dd}\u{17e0}-\u{17e9}\u{17f0}-\u{17f9}\u{1800}-\u{1819}\u{1820}-\u{1878}\u{1880}-\u{18aa}\u{18b0}-\u{18f5}\u{1900}-\u{191e}\u{1920}-\u{192b}\u{1930}-\u{193b}\u{1940}\u{1944}-\u{196d}\u{1970}-\u{1974}\u{1980}-\u{19ab}\u{19b0}-\u{19c9}\u{19d0}-\u{19da}\u{19de}-\u{1a1b}\u{1a1e}-\u{1a5e}\u{1a60}-\u{1a7c}\u{1a7f}-\u{1a89}\u{1a90}-\u{1a99}\u{1aa0}-\u{1aad}\u{1ab0}-\u{1ace}\u{1b00}-\u{1b4c}\u{1b50}-\u{1b7e}\u{1b80}-\u{1bf3}\u{1bfc}-\u{1c37}\u{1c3b}-\u{1c49}\u{1c4d}-\u{1c88}\u{1c90}-\u{1cba}\u{1cbd}-\u{1cc7}\u{1cd0}-\u{1cfa}\u{1d00}-\u{1f15}\u{1f18}-\u{1f1d}\u{1f20}-\u{1f45}\u{1f48}-\u{1f4d}\u{1f50}-\u{1f57}\u{1f59}\u{1f5b}\u{1f5d}\u{1f5f}-\u{1f7d}\u{1f80}-\u{1fb4}\u{1fb6}-\u{1fc4}\u{1fc6}-\u{1fd3}\u{1fd6}-\u{1fdb}\u{1fdd}-\u{1fef}\u{1ff2}-\u{1ff4}\u{1ff6}-\u{1ffe}\u{2000}-\u{2064}\u{2066}-\u{2071}\u{2074}-\u{208e}\u{2090}-\u{209c}\u{20a0}-\u{20c0}\u{20d0}-\u{20f0}\u{2100}-\u{218b}\u{2190}-\u{2426}\u{2440}-\u{244a}\u{2460}-\u{2b73}\u{2b76}-\u{2b95}\u{2b97}-\u{2cf3}\u{2cf9}-\u{2d25}\u{2d27}\u{2d2d}\u{2d30}-\u{2d67}\u{2d6f}-\u{2d70}\u{2d7f}-\u{2d96}\u{2da0}-\u{2da6}\u{2da8}-\u{2dae}\u{2db0}-\u{2db6}\u{2db8}-\u{2dbe}\u{2dc0}-\u{2dc6}\u{2dc8}-\u{2dce}\u{2dd0}-\u{2dd6}\u{2dd8}-\u{2dde}\u{2de0}-\u{2e5d}\u{2e80}-\u{2e99}\u{2e9b}-\u{2ef3}\u{2f00}-\u{2fd5}\u{2ff0}-\u{2ffb}\u{3000}-\u{303f}\u{3041}-\u{3096}\u{3099}-\u{30ff}\u{3105}-\u{312f}\u{3131}-\u{318e}\u{3190}-\u{31e3}\u{31f0}-\u{321e}\u{3220}-\u{a48c}\u{a490}-\u{a4c6}\u{a4d0}-\u{a62b}\u{a640}-\u{a6f7}\u{a700}-\u{a7ca}\u{a7d0}-\u{a7d1}\u{a7d3}\u{a7d5}-\u{a7d9}\u{a7f2}-\u{a82c}\u{a830}-\u{a839}\u{a840}-\u{a877}\u{a880}-\u{a8c5}\u{a8ce}-\u{a8d9}\u{a8e0}-\u{a953}\u{a95f}-\u{a97c}\u{a980}-\u{a9cd}\u{a9cf}-\u{a9d9}\u{a9de}-\u{a9fe}\u{aa00}-\u{aa36}\u{aa40}-\u{aa4d}\u{aa50}-\u{aa59}\u{aa5c}-\u{aac2}\u{aadb}-\u{aaf6}\u{ab01}-\u{ab06}\u{ab09}-\u{ab0e}\u{ab11}-\u{ab16}\u{ab20}-\u{ab26}\u{ab28}-\u{ab2e}\u{ab30}-\u{ab6b}\u{ab70}-\u{abed}\u{abf0}-\u{abf9}\u{ac00}-\u{d7a3}\u{d7b0}-\u{d7c6}\u{d7cb}-\u{d7fb}\u{d800}-\u{fa6d}\u{fa70}-\u{fad9}\u{fb00}-\u{fb06}\u{fb13}-\u{fb17}\u{fb1d}-\u{fb36}\u{fb38}-\u{fb3c}\u{fb3e}\u{fb40}-\u{fb41}\u{fb43}-\u{fb44}\u{fb46}-\u{fbc2}\u{fbd3}-\u{fd8f}\u{fd92}-\u{fdc7}\u{fdcf}\u{fdf0}-\u{fe19}\u{fe20}-\u{fe52}\u{fe54}-\u{fe66}\u{fe68}-\u{fe6b}\u{fe70}-\u{fe74}\u{fe76}-\u{fefc}\u{feff}\u{ff01}-\u{ffbe}\u{ffc2}-\u{ffc7}\u{ffca}-\u{ffcf}\u{ffd2}-\u{ffd7}\u{ffda}-\u{ffdc}\u{ffe0}-\u{ffe6}\u{ffe8}-\u{ffee}\u{fff9}-\u{fffd}\u{10000}-\u{1000b}\u{1000d}-\u{10026}\u{10028}-\u{1003a}\u{1003c}-\u{1003d}\u{1003f}-\u{1004d}\u{10050}-\u{1005d}\u{10080}-\u{100fa}\u{10100}-\u{10102}\u{10107}-\u{10133}\u{10137}-\u{1018e}\u{10190}-\u{1019c}\u{101a0}\u{101d0}-\u{101fd}\u{10280}-\u{1029c}\u{102a0}-\u{102d0}\u{102e0}-\u{102fb}\u{10300}-\u{10323}\u{1032d}-\u{1034a}\u{10350}-\u{1037a}\u{10380}-\u{1039d}\u{1039f}-\u{103c3}\u{103c8}-\u{103d5}\u{10400}-\u{1049d}\u{104a0}-\u{104a9}\u{104b0}-\u{104d3}\u{104d8}-\u{104fb}\u{10500}-\u{10527}\u{10530}-\u{10563}\u{1056f}-\u{1057a}\u{1057c}-\u{1058a}\u{1058c}-\u{10592}\u{10594}-\u{10595}\u{10597}-\u{105a1}\u{105a3}-\u{105b1}\u{105b3}-\u{105b9}\u{105bb}-\u{105bc}\u{10600}-\u{10736}\u{10740}-\u{10755}\u{10760}-\u{10767}\u{10780}-\u{10785}\u{10787}-\u{107b0}\u{107b2}-\u{107ba}\u{10800}-\u{10805}\u{10808}\u{1080a}-\u{10835}\u{10837}-\u{10838}\u{1083c}\u{1083f}-\u{10855}\u{10857}-\u{1089e}\u{108a7}-\u{108af}\u{108e0}-\u{108f2}\u{108f4}-\u{108f5}\u{108fb}-\u{1091b}\u{1091f}-\u{10939}\u{1093f}\u{10980}-\u{109b7}\u{109bc}-\u{109cf}\u{109d2}-\u{10a03}\u{10a05}-\u{10a06}\u{10a0c}-\u{10a13}\u{10a15}-\u{10a17}\u{10a19}-\u{10a35}\u{10a38}-\u{10a3a}\u{10a3f}-\u{10a48}\u{10a50}-\u{10a58}\u{10a60}-\u{10a9f}\u{10ac0}-\u{10ae6}\u{10aeb}-\u{10af6}\u{10b00}-\u{10b35}\u{10b39}-\u{10b55}\u{10b58}-\u{10b72}\u{10b78}-\u{10b91}\u{10b99}-\u{10b9c}\u{10ba9}-\u{10baf}\u{10c00}-\u{10c48}\u{10c80}-\u{10cb2}\u{10cc0}-\u{10cf2}\u{10cfa}-\u{10d27}\u{10d30}-\u{10d39}\u{10e60}-\u{10e7e}\u{10e80}-\u{10ea9}\u{10eab}-\u{10ead}\u{10eb0}-\u{10eb1}\u{10efd}-\u{10f27}\u{10f30}-\u{10f59}\u{10f70}-\u{10f89}\u{10fb0}-\u{10fcb}\u{10fe0}-\u{10ff6}\u{11000}-\u{1104d}\u{11052}-\u{11075}\u{1107f}-\u{110c2}\u{110cd}\u{110d0}-\u{110e8}\u{110f0}-\u{110f9}\u{11100}-\u{11134}\u{11136}-\u{11147}\u{11150}-\u{11176}\u{11180}-\u{111df}\u{111e1}-\u{111f4}\u{11200}-\u{11211}\u{11213}-\u{11241}\u{11280}-\u{11286}\u{11288}\u{1128a}-\u{1128d}\u{1128f}-\u{1129d}\u{1129f}-\u{112a9}\u{112b0}-\u{112ea}\u{112f0}-\u{112f9}\u{11300}-\u{11303}\u{11305}-\u{1130c}\u{1130f}-\u{11310}\u{11313}-\u{11328}\u{1132a}-\u{11330}\u{11332}-\u{11333}\u{11335}-\u{11339}\u{1133b}-\u{11344}\u{11347}-\u{11348}\u{1134b}-\u{1134d}\u{11350}\u{11357}\u{1135d}-\u{11363}\u{11366}-\u{1136c}\u{11370}-\u{11374}\u{11400}-\u{1145b}\u{1145d}-\u{11461}\u{11480}-\u{114c7}\u{114d0}-\u{114d9}\u{11580}-\u{115b5}\u{115b8}-\u{115dd}\u{11600}-\u{11644}\u{11650}-\u{11659}\u{11660}-\u{1166c}\u{11680}-\u{116b9}\u{116c0}-\u{116c9}\u{11700}-\u{1171a}\u{1171d}-\u{1172b}\u{11730}-\u{11746}\u{11800}-\u{1183b}\u{118a0}-\u{118f2}\u{118ff}-\u{11906}\u{11909}\u{1190c}-\u{11913}\u{11915}-\u{11916}\u{11918}-\u{11935}\u{11937}-\u{11938}\u{1193b}-\u{11946}\u{11950}-\u{11959}\u{119a0}-\u{119a7}\u{119aa}-\u{119d7}\u{119da}-\u{119e4}\u{11a00}-\u{11a47}\u{11a50}-\u{11aa2}\u{11ab0}-\u{11af8}\u{11b00}-\u{11b09}\u{11c00}-\u{11c08}\u{11c0a}-\u{11c36}\u{11c38}-\u{11c45}\u{11c50}-\u{11c6c}\u{11c70}-\u{11c8f}\u{11c92}-\u{11ca7}\u{11ca9}-\u{11cb6}\u{11d00}-\u{11d06}\u{11d08}-\u{11d09}\u{11d0b}-\u{11d36}\u{11d3a}\u{11d3c}-\u{11d3d}\u{11d3f}-\u{11d47}\u{11d50}-\u{11d59}\u{11d60}-\u{11d65}\u{11d67}-\u{11d68}\u{11d6a}-\u{11d8e}\u{11d90}-\u{11d91}\u{11d93}-\u{11d98}\u{11da0}-\u{11da9}\u{11ee0}-\u{11ef8}\u{11f00}-\u{11f10}\u{11f12}-\u{11f3a}\u{11f3e}-\u{11f59}\u{11fb0}\u{11fc0}-\u{11ff1}\u{11fff}-\u{12399}\u{12400}-\u{1246e}\u{12470}-\u{12474}\u{12480}-\u{12543}\u{12f90}-\u{12ff2}\u{13000}-\u{13455}\u{14400}-\u{14646}\u{16800}-\u{16a38}\u{16a40}-\u{16a5e}\u{16a60}-\u{16a69}\u{16a6e}-\u{16abe}\u{16ac0}-\u{16ac9}\u{16ad0}-\u{16aed}\u{16af0}-\u{16af5}\u{16b00}-\u{16b45}\u{16b50}-\u{16b59}\u{16b5b}-\u{16b61}\u{16b63}-\u{16b77}\u{16b7d}-\u{16b8f}\u{16e40}-\u{16e9a}\u{16f00}-\u{16f4a}\u{16f4f}-\u{16f87}\u{16f8f}-\u{16f9f}\u{16fe0}-\u{16fe4}\u{16ff0}-\u{16ff1}\u{17000}-\u{187f7}\u{18800}-\u{18cd5}\u{18d00}-\u{18d08}\u{1aff0}-\u{1aff3}\u{1aff5}-\u{1affb}\u{1affd}-\u{1affe}\u{1b000}-\u{1b122}\u{1b132}\u{1b150}-\u{1b152}\u{1b155}\u{1b164}-\u{1b167}\u{1b170}-\u{1b2fb}\u{1bc00}-\u{1bc6a}\u{1bc70}-\u{1bc7c}\u{1bc80}-\u{1bc88}\u{1bc90}-\u{1bc99}\u{1bc9c}-\u{1bca3}\u{1cf00}-\u{1cf2d}\u{1cf30}-\u{1cf46}\u{1cf50}-\u{1cfc3}\u{1d000}-\u{1d0f5}\u{1d100}-\u{1d126}\u{1d129}-\u{1d1ea}\u{1d200}-\u{1d245}\u{1d2c0}-\u{1d2d3}\u{1d2e0}-\u{1d2f3}\u{1d300}-\u{1d356}\u{1d360}-\u{1d378}\u{1d400}-\u{1d454}\u{1d456}-\u{1d49c}\u{1d49e}-\u{1d49f}\u{1d4a2}\u{1d4a5}-\u{1d4a6}\u{1d4a9}-\u{1d4ac}\u{1d4ae}-\u{1d4b9}\u{1d4bb}\u{1d4bd}-\u{1d4c3}\u{1d4c5}-\u{1d505}\u{1d507}-\u{1d50a}\u{1d50d}-\u{1d514}\u{1d516}-\u{1d51c}\u{1d51e}-\u{1d539}\u{1d53b}-\u{1d53e}\u{1d540}-\u{1d544}\u{1d546}\u{1d54a}-\u{1d550}\u{1d552}-\u{1d6a5}\u{1d6a8}-\u{1d7cb}\u{1d7ce}-\u{1da8b}\u{1da9b}-\u{1da9f}\u{1daa1}-\u{1daaf}\u{1df00}-\u{1df1e}\u{1df25}-\u{1df2a}\u{1e000}-\u{1e006}\u{1e008}-\u{1e018}\u{1e01b}-\u{1e021}\u{1e023}-\u{1e024}\u{1e026}-\u{1e02a}\u{1e030}-\u{1e06d}\u{1e08f}\u{1e100}-\u{1e12c}\u{1e130}-\u{1e13d}\u{1e140}-\u{1e149}\u{1e14e}-\u{1e14f}\u{1e290}-\u{1e2ae}\u{1e2c0}-\u{1e2f9}\u{1e2ff}\u{1e4d0}-\u{1e4f9}\u{1e7e0}-\u{1e7e6}\u{1e7e8}-\u{1e7eb}\u{1e7ed}-\u{1e7ee}\u{1e7f0}-\u{1e7fe}\u{1e800}-\u{1e8c4}\u{1e8c7}-\u{1e8d6}\u{1e900}-\u{1e94b}\u{1e950}-\u{1e959}\u{1e95e}-\u{1e95f}\u{1ec71}-\u{1ecb4}\u{1ed01}-\u{1ed3d}\u{1ee00}-\u{1ee03}\u{1ee05}-\u{1ee1f}\u{1ee21}-\u{1ee22}\u{1ee24}\u{1ee27}\u{1ee29}-\u{1ee32}\u{1ee34}-\u{1ee37}\u{1ee39}\u{1ee3b}\u{1ee42}\u{1ee47}\u{1ee49}\u{1ee4b}\u{1ee4d}-\u{1ee4f}\u{1ee51}-\u{1ee52}\u{1ee54}\u{1ee57}\u{1ee59}\u{1ee5b}\u{1ee5d}\u{1ee5f}\u{1ee61}-\u{1ee62}\u{1ee64}\u{1ee67}-\u{1ee6a}\u{1ee6c}-\u{1ee72}\u{1ee74}-\u{1ee77}\u{1ee79}-\u{1ee7c}\u{1ee7e}\u{1ee80}-\u{1ee89}\u{1ee8b}-\u{1ee9b}\u{1eea1}-\u{1eea3}\u{1eea5}-\u{1eea9}\u{1eeab}-\u{1eebb}\u{1eef0}-\u{1eef1}\u{1f000}-\u{1f02b}\u{1f030}-\u{1f093}\u{1f0a0}-\u{1f0ae}\u{1f0b1}-\u{1f0bf}\u{1f0c1}-\u{1f0cf}\u{1f0d1}-\u{1f0f5}\u{1f100}-\u{1f1ad}\u{1f1e6}-\u{1f202}\u{1f210}-\u{1f23b}\u{1f240}-\u{1f248}\u{1f250}-\u{1f251}\u{1f260}-\u{1f265}\u{1f300}-\u{1f6d7}\u{1f6dc}-\u{1f6ec}\u{1f6f0}-\u{1f6fc}\u{1f700}-\u{1f776}\u{1f77b}-\u{1f7d9}\u{1f7e0}-\u{1f7eb}\u{1f7f0}\u{1f800}-\u{1f80b}\u{1f810}-\u{1f847}\u{1f850}-\u{1f859}\u{1f860}-\u{1f887}\u{1f890}-\u{1f8ad}\u{1f8b0}-\u{1f8b1}\u{1f900}-\u{1fa53}\u{1fa60}-\u{1fa6d}\u{1fa70}-\u{1fa7c}\u{1fa80}-\u{1fa88}\u{1fa90}-\u{1fabd}\u{1fabf}-\u{1fac5}\u{1face}-\u{1fadb}\u{1fae0}-\u{1fae8}\u{1faf0}-\u{1faf8}\u{1fb00}-\u{1fb92}\u{1fb94}-\u{1fbca}\u{1fbf0}-\u{1fbf9}\u{20000}-\u{2a6df}\u{2a700}-\u{2b739}\u{2b740}-\u{2b81d}\u{2b820}-\u{2cea1}\u{2ceb0}-\u{2ebe0}\u{2f800}-\u{2fa1d}\u{30000}-\u{3134a}\u{31350}-\u{323af}\u{e0001}\u{e0020}-\u{e007f}\u{e0100}-\u{e01ef}\u{f0000}-\u{ffffd}\u{100000}-\u{10fffd}';
const VOUW: Record<number, string> = {0xb5: '\u03bc', 0xdf: 'ss', 0x149: '\u02bcn', 0x17f: 's', 0x1f0: 'j\u030c', 0x345: '\u03b9', 0x390: '\u03b9\u0308\u0301', 0x3b0: '\u03c5\u0308\u0301', 0x3c2: '\u03c3', 0x3d0: '\u03b2', 0x3d1: '\u03b8', 0x3d5: '\u03c6', 0x3d6: '\u03c0', 0x3f0: '\u03ba', 0x3f1: '\u03c1', 0x3f5: '\u03b5', 0x587: '\u0565\u0582', 0x13a0: '\u13a0', 0x13a1: '\u13a1', 0x13a2: '\u13a2', 0x13a3: '\u13a3', 0x13a4: '\u13a4', 0x13a5: '\u13a5', 0x13a6: '\u13a6', 0x13a7: '\u13a7', 0x13a8: '\u13a8', 0x13a9: '\u13a9', 0x13aa: '\u13aa', 0x13ab: '\u13ab', 0x13ac: '\u13ac', 0x13ad: '\u13ad', 0x13ae: '\u13ae', 0x13af: '\u13af', 0x13b0: '\u13b0', 0x13b1: '\u13b1', 0x13b2: '\u13b2', 0x13b3: '\u13b3', 0x13b4: '\u13b4', 0x13b5: '\u13b5', 0x13b6: '\u13b6', 0x13b7: '\u13b7', 0x13b8: '\u13b8', 0x13b9: '\u13b9', 0x13ba: '\u13ba', 0x13bb: '\u13bb', 0x13bc: '\u13bc', 0x13bd: '\u13bd', 0x13be: '\u13be', 0x13bf: '\u13bf', 0x13c0: '\u13c0', 0x13c1: '\u13c1', 0x13c2: '\u13c2', 0x13c3: '\u13c3', 0x13c4: '\u13c4', 0x13c5: '\u13c5', 0x13c6: '\u13c6', 0x13c7: '\u13c7', 0x13c8: '\u13c8', 0x13c9: '\u13c9', 0x13ca: '\u13ca', 0x13cb: '\u13cb', 0x13cc: '\u13cc', 0x13cd: '\u13cd', 0x13ce: '\u13ce', 0x13cf: '\u13cf', 0x13d0: '\u13d0', 0x13d1: '\u13d1', 0x13d2: '\u13d2', 0x13d3: '\u13d3', 0x13d4: '\u13d4', 0x13d5: '\u13d5', 0x13d6: '\u13d6', 0x13d7: '\u13d7', 0x13d8: '\u13d8', 0x13d9: '\u13d9', 0x13da: '\u13da', 0x13db: '\u13db', 0x13dc: '\u13dc', 0x13dd: '\u13dd', 0x13de: '\u13de', 0x13df: '\u13df', 0x13e0: '\u13e0', 0x13e1: '\u13e1', 0x13e2: '\u13e2', 0x13e3: '\u13e3', 0x13e4: '\u13e4', 0x13e5: '\u13e5', 0x13e6: '\u13e6', 0x13e7: '\u13e7', 0x13e8: '\u13e8', 0x13e9: '\u13e9', 0x13ea: '\u13ea', 0x13eb: '\u13eb', 0x13ec: '\u13ec', 0x13ed: '\u13ed', 0x13ee: '\u13ee', 0x13ef: '\u13ef', 0x13f0: '\u13f0', 0x13f1: '\u13f1', 0x13f2: '\u13f2', 0x13f3: '\u13f3', 0x13f4: '\u13f4', 0x13f5: '\u13f5', 0x13f8: '\u13f0', 0x13f9: '\u13f1', 0x13fa: '\u13f2', 0x13fb: '\u13f3', 0x13fc: '\u13f4', 0x13fd: '\u13f5', 0x1c80: '\u0432', 0x1c81: '\u0434', 0x1c82: '\u043e', 0x1c83: '\u0441', 0x1c84: '\u0442', 0x1c85: '\u0442', 0x1c86: '\u044a', 0x1c87: '\u0463', 0x1c88: '\ua64b', 0x1e96: 'h\u0331', 0x1e97: 't\u0308', 0x1e98: 'w\u030a', 0x1e99: 'y\u030a', 0x1e9a: 'a\u02be', 0x1e9b: '\u1e61', 0x1e9e: 'ss', 0x1f50: '\u03c5\u0313', 0x1f52: '\u03c5\u0313\u0300', 0x1f54: '\u03c5\u0313\u0301', 0x1f56: '\u03c5\u0313\u0342', 0x1f80: '\u1f00\u03b9', 0x1f81: '\u1f01\u03b9', 0x1f82: '\u1f02\u03b9', 0x1f83: '\u1f03\u03b9', 0x1f84: '\u1f04\u03b9', 0x1f85: '\u1f05\u03b9', 0x1f86: '\u1f06\u03b9', 0x1f87: '\u1f07\u03b9', 0x1f88: '\u1f00\u03b9', 0x1f89: '\u1f01\u03b9', 0x1f8a: '\u1f02\u03b9', 0x1f8b: '\u1f03\u03b9', 0x1f8c: '\u1f04\u03b9', 0x1f8d: '\u1f05\u03b9', 0x1f8e: '\u1f06\u03b9', 0x1f8f: '\u1f07\u03b9', 0x1f90: '\u1f20\u03b9', 0x1f91: '\u1f21\u03b9', 0x1f92: '\u1f22\u03b9', 0x1f93: '\u1f23\u03b9', 0x1f94: '\u1f24\u03b9', 0x1f95: '\u1f25\u03b9', 0x1f96: '\u1f26\u03b9', 0x1f97: '\u1f27\u03b9', 0x1f98: '\u1f20\u03b9', 0x1f99: '\u1f21\u03b9', 0x1f9a: '\u1f22\u03b9', 0x1f9b: '\u1f23\u03b9', 0x1f9c: '\u1f24\u03b9', 0x1f9d: '\u1f25\u03b9', 0x1f9e: '\u1f26\u03b9', 0x1f9f: '\u1f27\u03b9', 0x1fa0: '\u1f60\u03b9', 0x1fa1: '\u1f61\u03b9', 0x1fa2: '\u1f62\u03b9', 0x1fa3: '\u1f63\u03b9', 0x1fa4: '\u1f64\u03b9', 0x1fa5: '\u1f65\u03b9', 0x1fa6: '\u1f66\u03b9', 0x1fa7: '\u1f67\u03b9', 0x1fa8: '\u1f60\u03b9', 0x1fa9: '\u1f61\u03b9', 0x1faa: '\u1f62\u03b9', 0x1fab: '\u1f63\u03b9', 0x1fac: '\u1f64\u03b9', 0x1fad: '\u1f65\u03b9', 0x1fae: '\u1f66\u03b9', 0x1faf: '\u1f67\u03b9', 0x1fb2: '\u1f70\u03b9', 0x1fb3: '\u03b1\u03b9', 0x1fb4: '\u03ac\u03b9', 0x1fb6: '\u03b1\u0342', 0x1fb7: '\u03b1\u0342\u03b9', 0x1fbc: '\u03b1\u03b9', 0x1fbe: '\u03b9', 0x1fc2: '\u1f74\u03b9', 0x1fc3: '\u03b7\u03b9', 0x1fc4: '\u03ae\u03b9', 0x1fc6: '\u03b7\u0342', 0x1fc7: '\u03b7\u0342\u03b9', 0x1fcc: '\u03b7\u03b9', 0x1fd2: '\u03b9\u0308\u0300', 0x1fd3: '\u03b9\u0308\u0301', 0x1fd6: '\u03b9\u0342', 0x1fd7: '\u03b9\u0308\u0342', 0x1fe2: '\u03c5\u0308\u0300', 0x1fe3: '\u03c5\u0308\u0301', 0x1fe4: '\u03c1\u0313', 0x1fe6: '\u03c5\u0342', 0x1fe7: '\u03c5\u0308\u0342', 0x1ff2: '\u1f7c\u03b9', 0x1ff3: '\u03c9\u03b9', 0x1ff4: '\u03ce\u03b9', 0x1ff6: '\u03c9\u0342', 0x1ff7: '\u03c9\u0342\u03b9', 0x1ffc: '\u03c9\u03b9', 0xab70: '\u13a0', 0xab71: '\u13a1', 0xab72: '\u13a2', 0xab73: '\u13a3', 0xab74: '\u13a4', 0xab75: '\u13a5', 0xab76: '\u13a6', 0xab77: '\u13a7', 0xab78: '\u13a8', 0xab79: '\u13a9', 0xab7a: '\u13aa', 0xab7b: '\u13ab', 0xab7c: '\u13ac', 0xab7d: '\u13ad', 0xab7e: '\u13ae', 0xab7f: '\u13af', 0xab80: '\u13b0', 0xab81: '\u13b1', 0xab82: '\u13b2', 0xab83: '\u13b3', 0xab84: '\u13b4', 0xab85: '\u13b5', 0xab86: '\u13b6', 0xab87: '\u13b7', 0xab88: '\u13b8', 0xab89: '\u13b9', 0xab8a: '\u13ba', 0xab8b: '\u13bb', 0xab8c: '\u13bc', 0xab8d: '\u13bd', 0xab8e: '\u13be', 0xab8f: '\u13bf', 0xab90: '\u13c0', 0xab91: '\u13c1', 0xab92: '\u13c2', 0xab93: '\u13c3', 0xab94: '\u13c4', 0xab95: '\u13c5', 0xab96: '\u13c6', 0xab97: '\u13c7', 0xab98: '\u13c8', 0xab99: '\u13c9', 0xab9a: '\u13ca', 0xab9b: '\u13cb', 0xab9c: '\u13cc', 0xab9d: '\u13cd', 0xab9e: '\u13ce', 0xab9f: '\u13cf', 0xaba0: '\u13d0', 0xaba1: '\u13d1', 0xaba2: '\u13d2', 0xaba3: '\u13d3', 0xaba4: '\u13d4', 0xaba5: '\u13d5', 0xaba6: '\u13d6', 0xaba7: '\u13d7', 0xaba8: '\u13d8', 0xaba9: '\u13d9', 0xabaa: '\u13da', 0xabab: '\u13db', 0xabac: '\u13dc', 0xabad: '\u13dd', 0xabae: '\u13de', 0xabaf: '\u13df', 0xabb0: '\u13e0', 0xabb1: '\u13e1', 0xabb2: '\u13e2', 0xabb3: '\u13e3', 0xabb4: '\u13e4', 0xabb5: '\u13e5', 0xabb6: '\u13e6', 0xabb7: '\u13e7', 0xabb8: '\u13e8', 0xabb9: '\u13e9', 0xabba: '\u13ea', 0xabbb: '\u13eb', 0xabbc: '\u13ec', 0xabbd: '\u13ed', 0xabbe: '\u13ee', 0xabbf: '\u13ef', 0xfb00: 'ff', 0xfb01: 'fi', 0xfb02: 'fl', 0xfb03: 'ffi', 0xfb04: 'ffl', 0xfb05: 'st', 0xfb06: 'st', 0xfb13: '\u0574\u0576', 0xfb14: '\u0574\u0565', 0xfb15: '\u0574\u056b', 0xfb16: '\u057e\u0576', 0xfb17: '\u0574\u056d'};

const T = `[${TOEGEWEZEN}]`;
// U+1171E heet in 15.0 Mn (in 16.0 Mc); U+0295 is in 15.0 een kleine letter (in 16.0 niet meer)
const MN_OOK = 0x1171e;
const KLEIN_OOK = 0x295;
const ONBEKEND = new RegExp(`[^${TOEGEWEZEN}]`, 'u');
const ONBEKEND_STUK = new RegExp(`([^${TOEGEWEZEN}]+)`, 'u');
const ALNUM = new RegExp(`^[[\\p{L}\\p{N}]&&${T}]$`, 'v');
const ALPHA = new RegExp(`^[[\\p{L}]&&${T}]+$`, 'v');
const BOVEN = new RegExp(`^[\\p{Uppercase}&&${T}]$`, 'v');
const ONDER = new RegExp(`^[[\\p{Lowercase}&&${T}]\\u{295}]$`, 'v');
const TITEL = new RegExp(`^[\\p{Lt}&&${T}]$`, 'v');
const MN = new RegExp(`^[[\\p{Mn}&&${T}]\\u{1171e}]$`, 'v');
const MN_ALLE = new RegExp(`[[\\p{Mn}&&${T}]\\u{1171e}]`, 'gv');
const M = new RegExp(`^[\\p{M}&&${T}]$`, 'v');
// Voor een regex: een teken dat Python `isalnum` noemt (`[^\W_]`), en een dat het niet noemt (`[\W_]`); v-modus.
export const ALNUM_KLASSE = `[[\\p{L}\\p{N}]&&${T}]`;
export const GEEN_ALNUM_KLASSE = `[^[\\p{L}\\p{N}]&&${T}]`;
// Wat Python witruimte noemt (`str.isspace`, `str.split()`).
const WIT_TEKENS = '\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';
const WIT = new RegExp(`^[${WIT_TEKENS}]$`, 'u');
const WIT_RAND = new RegExp(`^[${WIT_TEKENS}]+|[${WIT_TEKENS}]+$`, 'gu');
const WIT_BEGIN = new RegExp(`^[${WIT_TEKENS}]+`, 'u');
const WIT_EIND = new RegExp(`[${WIT_TEKENS}]+$`, 'u');
const WIT_ERGENS = new RegExp(`[${WIT_TEKENS}]`, 'u');

export const isalnum = (c: string): boolean => ALNUM.test(c);
export const isalpha = (s: string): boolean => ALPHA.test(s);
export const isMn = (c: string): boolean => MN.test(c);
export const isM = (c: string): boolean => M.test(c);
export const isspace = (c: string): boolean => WIT.test(c);
export const heeftWit = (s: string): boolean => WIT_ERGENS.test(s);
export const isascii = (s: string): boolean => /^[\x00-\x7f]*$/.test(s);

// `str.isupper()`: minstens één hoofdletter, en geen kleine letter of titelletter.
export function isupper(s: string): boolean {
  let hoofd = false;
  for (const c of s) {
    if (ONDER.test(c) || TITEL.test(c)) return false;
    if (BOVEN.test(c)) hoofd = true;
  }
  return hoofd;
}

// Een tekst in stukken: wat 15.0 kent, en wat het niet kent (dat blijft zoals het is).
function inStukken(s: string, f: (stuk: string) => string): string {
  if (!ONBEKEND.test(s)) return f(s);
  return s.split(ONBEKEND_STUK).map((stuk, i) => (i % 2 ? stuk : f(stuk))).join('');
}

export const lower = (s: string): string => inStukken(s, (x) => x.toLowerCase());
export const normaliseer = (s: string, vorm: 'NFC' | 'NFD' | 'NFKC' | 'NFKD'): string => inStukken(s, (x) => x.normalize(vorm));
export const zonderMn = (s: string): string => s.replace(MN_ALLE, '');

// `str.casefold()`: per teken, zonder samenhang (anders dan `lower`, dat een slot-sigma kent).
export function casefold(s: string): string {
  let uit = '';
  for (const c of s) {
    const cp = c.codePointAt(0)!;
    const v = VOUW[cp];
    uit += v !== undefined ? v : ONBEKEND.test(c) ? c : c.toLowerCase();
  }
  return uit;
}

// `str.strip()`, `lstrip()`, `rstrip()` zonder argument: witruimte; met tekens: die tekens.
export const strip = (s: string): string => s.replace(WIT_RAND, '');
export const lstrip = (s: string): string => s.replace(WIT_BEGIN, '');
export const rstrip = (s: string): string => s.replace(WIT_EIND, '');

export function stripTekens(s: string, tekens: string, kant: 'beide' | 'links' | 'rechts' = 'beide'): string {
  const set = new Set(Array.from(tekens));
  const t = Array.from(s);
  let a = 0;
  let b = t.length;
  if (kant !== 'rechts') while (a < b && set.has(t[a])) a++;
  if (kant !== 'links') while (b > a && set.has(t[b - 1])) b--;
  return t.slice(a, b).join('');
}

// Python vergelijkt teksten op code points; JavaScript op UTF-16. Alleen een surrogaat tegen U+E000 tot U+FFFF verschilt.
export function vergelijk(a: string, b: string): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    const x = a.charCodeAt(i);
    const y = b.charCodeAt(i);
    if (x !== y) {
      const fx = x >= 0xd800 && x <= 0xdfff ? x + 0x2000 : x >= 0xe000 ? x - 0x800 : x;
      const fy = y >= 0xd800 && y <= 0xdfff ? y + 0x2000 : y >= 0xe000 ? y - 0x800 : y;
      return fx - fy;
    }
  }
  return a.length - b.length;
}

// Lengte en stukken in code points, zoals Python telt.
export const lengte = (s: string): number => {
  let n = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c < 0xd800 || c > 0xdbff || i + 1 >= s.length) n++;
    else { const d = s.charCodeAt(i + 1); n++; if (d >= 0xdc00 && d <= 0xdfff) i++; }
  }
  return n;
};
export const knip = (s: string, van: number, tot?: number): string => {
  if (!/[\ud800-\udfff]/.test(s)) return s.slice(van, tot);
  return Array.from(s).slice(van, tot).join('');
};

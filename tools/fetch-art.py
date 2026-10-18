#!/usr/bin/env python3
"""Download the Pip-Boy art into barry/art/ for the app to use.

The Vault Boy, S.P.E.C.I.A.L. and weapon pictures are Bethesda's, so this
repository does not carry them. Each is a one-color mask: white, with the
picture's brightness as its opacity. The app paints the mask in the game's
Pip-Boy color (qml/PipArt.qml), the way the game shows its pictures.
art/weapons.json names the weapons of each weapon picture, for the service
to match the game's weapons with (service.py weapon_picture).

    python3 -I tools/fetch-art.py

downloads the finished masks: one bundle (BUNDLE), checked against its hash,
from this repository's art-N release. The build runs this before packing
(.github/workflows/barry-app.yml). Without barry/art/ the app still works
and draws its own plain figure.

    python3 -I tools/fetch-art.py --from-sources [BUNDLE.tar.gz]

makes the masks from the pictures themselves (needs Pillow), each checked
against its hash, and writes the bundle for a new art-N release:

- The Vault Boy and S.P.E.C.I.A.L.: aviralmehrotra/Fallout4-Pip-Boy at a
  fixed commit.
- The weapons: the Fallout Wiki (fallout.wiki), one picture for each Fallout 4
  weapon page that has one (base game, add-ons and Creation Club). The wiki
  turns away GitHub's build machines, which is why the build uses the bundle.

Then upload the bundle to a new art-N release and change BUNDLE here.
"""

import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile

# The finished masks: the art-N release asset and its hash.
BUNDLE = ("https://github.com/project-barry/PyPipboyApp/releases/download/art-1/pipboy-art-1.tar.gz",
          "59b5860dec35d132b9dabff42de3b93c47d663b5590b2f53ac6ca4f4297db810")

REPO = "aviralmehrotra/Fallout4-Pip-Boy"
COMMIT = "246bd9f17d9b4648e7ef410c4c3b5cca84689796"
WIKI = "https://images.fallout.wiki/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "barry", "art")

# Where each picture goes in barry/art/, where it comes from, and its hash.
ART = {
    "vaultboy.png": ("img/stat/vaultboy2.png", "d227d5ca25b7c51b6d8e00b32c13398a0895e63227e0efdb0133204be02d527f"),
    "special/strength.png": ("img/stat-special/Strength_FO4.webp", "3011ada43003bd5876173310a6f4d2c04b29a0cc2913b4ec1842cf3f0777daa1"),
    "special/perception.png": ("img/stat-special/Perception_FO4.webp", "6f526f3c8f683291e0bee792de08fa67469ad980573af045847e90380643883d"),
    "special/endurance.png": ("img/stat-special/Endurance_FO4.webp", "10a7e1dc1bb43dcff10bd64a4b7f16dc461cd13dd497c92f4c54b41e698954a2"),
    "special/charisma.png": ("img/stat-special/Charisma_FO4.webp", "54d75f295060e4ba93f843e80e3ebefdf1a8bb9a1e84ca9eb1fb04e073eccf1e"),
    "special/intelligence.png": ("img/stat-special/Intelligence_FO4.webp", "9333ef64e6d276aeb4cb633178fb0c1be0969cda34325e3e5ca5454d4946bc5e"),
    "special/agility.png": ("img/stat-special/Agility_FO4.webp", "74abd6af7eb25ed2b3ec0ed39f53c9616445c1e8e2a22aa71555f81f5979a6f1"),
    "special/luck.png": ("img/stat-special/Luck_FO4.webp", "94c3ae121dedaa5e0f33ba1b7f9e984fcff0a50d03529047d619a8284d6f0891"),
}

# The weapons: art/weapons/NAME.png, the wiki file (under WIKI), its hash, and
# the names of the weapons it shows (the wiki's page names, without the
# "(Fallout 4)" and the like). Made from the wiki's Fallout 4 weapon
# categories on 2026-10-18; its "coming soon" placeholders are left out.
WEAPONS = [
    ("10mm-pistol", "c/c8/Fallout4_10mm_pistol.png", "ea38305949648c362cc44d2a171bc4127bff1d145ec1d8cb4d7e595c0ba9556c",
     ["10mm Pistol"]),
    ("2076-world-series-baseball-bat", "0/03/Fo4_2076_bat.png", "26ec2118bce70e5a4d542ceed2039eca2f1f41813bd6b5082b642178bc067953",
     ["2076 World Series Baseball Bat"]),
    ("44-pistol", "5/50/FO4_Weapon_.44_Snubnose.webp", "9c51712acb991b3eff6fa33bcbc7c09330fb3a00958d8c5f6f7663fcaee3f2ce",
     [".44 Pistol"]),
    ("acid-soaker", "f/f2/Acidsoaker.png", "704998c0a62470829c2e3780b9694085975672871deed15d5932537c24d2503e",
     ["Acid Soaker"]),
    ("aeternus", "2/2e/Gatling_laser_%28Fallout_4%29.png", "b16650cc242232306cebba2ddfa0f2e19b491eaea0218f6b378bf19befd5ba87",
     ["Aeternus", "Final Judgment", "Gatling Laser"]),
    ("alien-atomizer", "9/9a/CC_Atomizer.png", "1b460574423190397a073fa810b1b9b31abe418b4fb3d48492234cabc4e84b9e",
     ["Alien Atomizer"]),
    ("alien-disintegrator", "d/da/Fo4CC_alien_disintegrator.png", "720648aee4508a6a0fed16afdf11bde3fb9f148caabd34ffaac61c6c32a8dfcd",
     ["Alien Disintegrator"]),
    ("alien-shock-baton", "d/d1/Fo4CC_alien_shock_baton.png", "5bfcbd5197048a20f5905f6367526011a0d9c5aa2f0adcfaadc73aaaba8169ff",
     ["Alien Shock Baton"]),
    ("anti-materiel-rifle", "a/a9/Fo4CC_anti-materiel_rifle.png", "9c13e75a168dbfa0febac9fdd4981f6140d76e07137b23b6898701288edcfc41",
     ["Anti-Materiel Rifle", "Hunter's Anti-Materiel Rifle", "Penetrating Anti-Materiel Rifle"]),
    ("artillery-smoke-grenade", "5/51/VirtyandArtillery_Smoke_Grenade.png", "1bbed58f62f21d419eb329ccc7ae055ce426febfd1bc4340898418de76c0e00f",
     ["Artillery Smoke Grenade", "Vertibird Signal Grenade"]),
    ("assault-rifle", "7/78/AssaultrifleFO4.png", "eee84e331a998e33668f7a95f655d1a033abf222c1d1e5e1e90bb2f7d63734a1",
     ["Assault Rifle"]),
    ("assaultron-blade", "b/b4/Automatron_assaultron_blade.png", "f5b37ca8f080a1c32a7b339eda6da1a2d44285ab19f0094527ffaa05e10b04b6",
     ["Assaultron Blade"]),
    ("atoms-judgement", "4/4a/Atoms_Judgement.png", "f6592edaa29ea9f0b9314accd81ee5e7a7eb1cc55c51c41744a06cc2880329dc",
     ["Atom's Judgement"]),
    ("baseball-grenade", "e/ee/Baseball_grenade.png", "da478c480838ae58c541197e3f30d2bb6b8244420c5da6f2dfc5a9e8df52db57",
     ["Baseball Grenade"]),
    ("baseball-launcher", "7/7b/FO4CC_Weapon_Baseball_Launcher_Front.webp", "ca1797c4261d19f8b7bf8a1717e6beebb8a8c27e4a07f056a81e1e89b5d3cf82",
     ["Baseball Launcher"]),
    ("baton", "5/5e/Fallout4_Security_Baton.png", "a41151d79e11958004855dfd7ca2188fa6e44c239d6f41e20a744ba8c992f047",
     ["Baton"]),
    ("bear-trap", "a/a9/Fo4FH_bear_trap.png", "ab2def938c6688abfd2219e3dcf8f9be81685e1f8d05fd5219952c7a1571ffbc",
     ["Bear Trap"]),
    ("bfg9000", "d/de/BFG9000.png", "d915d910009c76b0ddb26f7a5a5733d2c129691d9e099549e7461c249a7cef98",
     ["BFG9000"]),
    ("big-boy", "f/fb/Fallout4_Fat_man.png", "3c2be727c01dba1eed3087d14416bc5c6c489b635027e2ea9ad942aaca7b5022",
     ["Big Boy", "Fat Man"]),
    ("big-jim", "6/61/Fallout4_Pipe_wrench.png", "43fa3ddf3f697a36f304c4c31f024928f504fd56fb01bc5a350bbf19c3163069",
     ["Big Jim", "Pipe Wrench"]),
    ("bleeding-bear-trap", "9/92/Bleeding_bear_trap.png", "1f01eadec8896eff9853bd07d4d14d8e48860c540ca82afc19ae6397b87e396a",
     ["Bleeding Bear Trap"]),
    ("board", "5/5e/Board.png", "76b15a19202243c4fbec602d47dd7030d21f03c3d8d2b4cad8ee5952527bae5f",
     ["Board"]),
    ("boxing-glove", "c/c4/Fallout4_boxing_glove.png", "2ccf90ab363276864a31cb9514cad82e8d931efe7816b0398d78cf5a80b032ba",
     ["Boxing Glove"]),
    ("broadsider", "9/98/Broadsider.png", "d99c4ec5b49351b3dc0e220e13f18c42cf2553a43fe318db55f1634c10725bd7",
     ["Broadsider"]),
    ("caltrops", "3/31/Caltrops.png", "2bdeed100e18ad1ace99f1766bee4c532d7d06b0c425f639462fd74ae434bfca",
     ["Caltrops"]),
    ("chinese-grenade-launcher-rifle", "7/7e/FOCC_Weapon_Chinese_Grenade_Launcher_Rifle_Left.webp", "c30de9578e9af6aebcb8c8300a9ad67b85b243686cb5db31fa70d5e046fc285f",
     ["Chinese Grenade Launcher Rifle"]),
    ("citos-shiny-slugger", "6/6b/Cito%27sShinySlugger-NukaWorld-Melee.png", "83db4a1722cdaba586f2e3b3f3b724065db2c3e21ee2e4ac6e1ea219c3308514",
     ["Cito's Shiny Slugger"]),
    ("classic-10mm-pistol", "9/90/Classic_10mm_pistol.png", "09cd6308b44a210d87cdbb14cb1c7dca5e10c02695822c992e28b94e6e3ab34e",
     ["Classic 10mm Pistol"]),
    ("combat-knife", "2/24/Fallout4_Combat_knife.png", "b9481eeb52389e3f1cf8132dbdc5f3b77fafeb75e18c90ed41a94ab3d2fa0d68",
     ["Combat Knife"]),
    ("combat-rifle", "6/67/Fallout4_Combat_rifle.png", "6a92ffd7c506c64323789cbd95681677d92345dfccb9ea79975003e2979e5a82",
     ["Combat Rifle", "December's Child"]),
    ("combat-shotgun", "1/13/Fo4_combat_shotgun_standard.png", "fba337d72df1f6837659bd6fff6abf23c41e4b3abcc364dabe1110922f9c5c6d",
     ["Combat Shotgun"]),
    ("commie-whacker", "d/d9/Commie_Whacker.png", "a6047f04a968528c7c4d306a1452e5db0d25cbad86594c68a21c0485136e70b7",
     ["Commie Whacker"]),
    ("cosmic-cannon", "9/96/Cosmic_cannon.png", "990b56111019c49388505388adad7657f5f76292c160aedfbf0aa07bd03fe9dc",
     ["Cosmic Cannon"]),
    ("cr-74l", "2/27/CR-74L.png", "9182bc39b52fcc78cec640f3a5d6b5adc092af64ec111b9f5605059ae7487d95",
     ["CR-74L"]),
    ("cryo-mine", "a/a3/Cryomine.webp", "5895486ac80cfd656057ddbb8342bc00ca938209bc5132a590decb461a407513",
     ["Cryo Mine"]),
    ("cryogenic-grenade", "8/8c/Cryogenic_grenade.png", "88e2218738b6e7ae327d803233722cbf4e81338672a1fbd560394241f6125f27",
     ["Cryogenic Grenade"]),
    ("cryolator", "c/c2/Cryolator_%28Fallout_4%29.png", "7ada2bf4e76dfef43f16afd34040e216e9b4117765e9fc6a6cef138a3563c273",
     ["Cryolator"]),
    ("deathclaw-gauntlet", "4/42/Deathclaw_gauntlet_%28Fallout_4%29.png", "c872caed876a37be78782229c879074c659955571e9b49df50737950aad9a91f",
     ["Deathclaw Gauntlet"]),
    ("deliverer", "1/15/The_Deliverer.png", "c50db4048bc77c00ed93effffa9835e6b7ba96162a98b3703fa1bb95d0adc8b8",
     ["Deliverer"]),
    ("double-barrel-shotgun", "7/7b/Double-barrel_shotgun_%28Fallout_4%29.png", "af8f4127169bd2fc575a55af2fc9fe22b9dca4ebe0cd9598a2d0580cd6ecb483",
     ["Double-Barrel Shotgun"]),
    ("early-retirement", "8/82/Early_Retirement.png", "0dbb9fafbeb4efd3d63d2bbfe3fa8d327d60d31fd0c3a18a76cf0d530a6a1cfd",
     ["Early Retirement"]),
    ("eddies-peace", "e/e6/Eddies_Peace.png", "82bba978bcc0941956eec9850ed9da8b89a404f084db4c61fc8a7e94bcdeec41",
     ["Eddie's Peace"]),
    ("experiment-18-a", "1/14/Plasma_gun.png", "7d3c2505ed8223732e7cedef3318057f193593515825753a9f884bc492caecd6",
     ["Experiment 18-A"]),
    ("fencebuster", "5/50/Fencebuster.png", "7372c4c5d92ed608cbcb742279f2760a00545752d6679adbb0cd9b2609b080ea",
     ["Fencebuster"]),
    ("flamer", "8/8d/Flamer_%28Fallout_4%29.png", "1d312ef84daf57162167f0bcd7dd0d3626882c9ec64e9f884bd11a2f6cfe11f3",
     ["Flamer", "Sergeant Ash"]),
    ("flare-gun", "c/c1/Fallout4_Flare_gun.png", "0fed8b67aca1f8515351b35176ff8496ad7835ac6472629185af562eee82dc6a",
     ["Flare Gun"]),
    ("fragmentation-grenade", "5/51/Fragmentation_grenade_%28Fallout_4%29.png", "871c799f4ca19b79a68fe77f49fdcd07b2e4397db40b4fe3e39efa6e24385e01",
     ["Fragmentation Grenade"]),
    ("fragmentation-grenade-mirv", "8/88/FragmentationMIRV-NukaWorld.png", "339ee0fb59a9dcf3046fa85622f2b69f7c8e88aa9e7d2f23de50e1a1da94e590",
     ["Fragmentation Grenade MIRV"]),
    ("fragmentation-mine", "8/81/Fragmine.webp", "ee425ab216d669ab6e60409b25ff8ede55ba0d3b787a9e18bdc778eafbbc8240",
     ["Fragmentation Mine"]),
    ("fury-grenade", "3/3c/FuryGrenade-NukaWorld.png", "3a49a003d56038ab191e2efd45f0b65da97db3d2ed7da94cc45073706f3073f1",
     ["Fury Grenade"]),
    ("gauss-rifle", "a/a3/FO4_Weapon_Gauss_Rifle.webp", "ce174179a658aae68c246576bc831b77631b6f2704f71ba336baecae6760302c",
     ["Gauss Rifle"]),
    ("gen-4-10mm-pistol", "6/6c/FO4CC_Gen-4_10mm_pistol.png", "5dd2d144c9d82d1f13d74416f2d9c69763655a17e9b5f67005729c2cd2813e87",
     ["Gen-4 10mm Pistol"]),
    ("general-chaos-revenge", "0/00/FO4_Weapon_General_Chao%27s_Revenge.webp", "fe49b1e89ef7f9bab6aec5121172344d8e9932cd08b4f5793be797a545ac3af0",
     ["General Chao's Revenge"]),
    ("good-intentions", "8/8b/Good_Intentions.png", "ef93c22aa7c449192eca67083e9a6e7c57c33332684d7e3183bcf620c89f20f2",
     ["Good Intentions"]),
    ("grognaks-axe", "7/7c/FO4_Grognak_axe.png", "d274b0d579849204f48049ffa990c4e5e8a88b0d73116e6b51f698090ba87a47",
     ["Grognak's Axe"]),
    ("hallucigen-gas-grenade", "6/61/HalluciGen_gas_grenade.png", "d1c9293b9c62a69e054f65471f90d6378156d3620c4e3dd2e6f8eef0c73c1912",
     ["HalluciGen Gas Grenade"]),
    ("handmade-rifle", "e/e7/FO4NW_Handmade_rifle.png", "5afedc71785412b9eb0ee9588be87bdd3cb20f4aaf3570c45afa1070caf05d8e",
     ["Handmade Rifle"]),
    ("handmade-shotgun", "0/0f/Handmade_shotgun.png", "2ed933f0392bddc7aac763b12341c14e9e0158fb3ed6f223549f5c52df5f82ff",
     ["Handmade Shotgun"]),
    ("harpoon-gun", "0/0b/Harpoon_gun.png", "d473f15912857094a168ce1dfc34fc5f2acc25cf2ceabdad94870476077e65c6",
     ["Admiral's Friend", "Defender's Harpoon Gun", "Harpoon Gun", "Skipper's Last Stand"]),
    ("heavy-incinerator", "b/ba/Fo4CC_Heavy_incinerator.png", "a0b33422d4941c7efbb5413811160708209a9722436f697eaaed73198fd3be57",
     ["Heavy Incinerator"]),
    ("homing-beacon", "b/b1/Homing_Beacon.png", "6d9678de9669880a88f0d22141e22cedc83c91c069dae7ded13eeac8e358750d",
     ["Homing Beacon"]),
    ("hubs-alien-blaster", "7/71/Alien_blaster_pistol.png", "88c71e5d47e6d8c9bc47468a6f35496bb9289b5da85dd5c4e1691d142c8eda3f",
     ["Alien Blaster Pistol", "Hub's Alien Blaster"]),
    ("hunting-rifle", "a/a2/Standard_hunting_rifle_fo4.png", "3213810d0339cfa1ac924585d6478cece0d9968c7eafc251f0dc5885f0cd32b4",
     ["Hunting Rifle"]),
    ("institute-beacon", "3/35/FO4_Institute_Pulse_grenade.png", "df474f131809de7baba4f304317c5d8dc5b146afaaf5cd506b2c5e885bacdde8",
     ["Institute Beacon", "Synth Relay Grenade"]),
    ("institute-laser", "b/bf/Fallout4_Institute_pistol.png", "8b8fcbf46009e66c6a2bb49a4b42f786c6683fbc1cda701f9b7b280c365190f4",
     ["Institute Laser"]),
    ("ion-gun", "f/f3/Ion_Gun.webp", "84ee958a886b213fd4c7a15be1d97ba7dff4159af3c59c36f64d65c7e66014e4",
     ["Ion Gun"]),
    ("junk-jet", "8/87/Fallout4_junk_jet.png", "b1bf168c1115ccd1e556a8deb312ba96236bca273dcd9db098c456f45380d6f9",
     ["Junk Jet"]),
    ("justice", "f/f6/Fo4_justice.png", "4232e65538e164d53689e8ae4ada917c19d9528f76a35ab8c40ad1771612bae4",
     ["Justice"]),
    ("kelloggs-pistol", "3/38/Kelloggs_pistol.png", "01aab6c2a789ec37f6df438a1e9d94a4afc03e005591e37d8bdc2a7ba0d88928",
     ["Kellogg's Pistol"]),
    ("knuckles", "3/39/Fallout4_Knuckles.png", "dd9d4211a59e50a89dde74453d783a3b92da8e47a165ae070be85c9b1a8fb595",
     ["Knuckles"]),
    ("kremvhs-tooth", "8/86/Kremvh%27s_Tooth.png", "52fe7eeb84caa3e6f799c63f861d16ac168dca389a88e1a0e3da067cba053bbc",
     ["Kremvh's Tooth"]),
    ("laser-gun", "3/3c/Fallout4_laser_pistol.png", "1584cea73773d352aadf9ca0482638eea30a341504258b2a61644dfc7719e49a",
     ["Laser Gun", "Old Faithful", "Prototype UP77 \"Limitless Potential\""]),
    ("laser-musket", "1/16/FO4LaserMusket.png", "defcdfd326049a7fe597e03c877f4abeb65b52c89a2d93ba043876cb1b7ce2ed",
     ["Laser Musket"]),
    ("le-fusil-terribles", "8/84/Le_Fusil_Terribles.png", "62583833127939617fbb10d5f4bd3b05d8685d35d1a25efc12553613f8d3dc28",
     ["Le Fusil Terribles"]),
    ("lead-pipe", "4/47/Fo4_lead_pipe.png", "f1a217e0050f2d81744c2deeffcf432f082b099e0435576d98c4aa8c2ba41160",
     ["Lead Pipe"]),
    ("lever-action-rifle", "a/a2/FO4FH_Lever_action_rifle.png", "2df8f330987d1ff8b0a64b18407f7b7c93ea03a3d699525db98af8eaa2f5076c",
     ["Lever Action Rifle"]),
    ("lorenzos-artifact-gun", "c/c1/Lorenzos_artifact_gun.png", "3a6c0d95b7f31dbc00ecb1cd1f7b1f4759fe4f048f84856a6a05e89fd4cbfb90",
     ["Lorenzo's Artifact Gun"]),
    ("lucky-eddy", "a/af/Fo4FH_lever_action_rifle.png", "c87a6c555bfe2b4e64dd12b808d5d646af0d9205640290362877aa4af7944b0c",
     ["Lucky Eddy"]),
    ("machete", "c/cf/FO76_Machete.png", "488978a5efb7c1ceeaa77937b79889e98825965ee607298320a7671cbd6471a0",
     ["Machete"]),
    ("manwell-carbine", "e/e1/FO4CC_Manwell_carbine.png", "99370a9fbe0be3c5d361e6fb5fa1f28f7958570ecb548374083b598d6d82b94f",
     ["Manwell Carbine"]),
    ("manwell-rifle", "c/c6/FO4CC_Manwell_rifle.png", "b5580ed42a2ef41c1220ea60631fafbac2ef73fb97cb616c51cd9b8373f8bc58",
     ["Manwell Rifle"]),
    ("meat-hook", "5/58/Meat_hook.png", "4e3d572f611dfe4d02bb75109f60c0637de946aa42c81b6e4e5ca9d78e9bd902",
     ["Butcher's Hook", "Meat Hook"]),
    ("minigun", "5/50/Fallout4_Minigun.png", "9c3c8990f9ba11227cb1a78e5d213196a93da23a665f0764e6e3105e3dd40720",
     ["Ashmaker", "Minigun"]),
    ("molotov-cocktail", "3/3d/Fo4_Molotov_cocktail.png", "70f9810594ab71f29123b7c9b998d51e686b7ba183305802973173289cc36d2b",
     ["Molotov Cocktail"]),
    ("mr-handy-buzz-blade", "1/13/Mr._Handy_buzz_blade.png", "3e496e42a1b280642cdf786321b0b7b34a23bb8b7881ecb06501877c8b3f57c3",
     ["Mr. Handy Buzz Blade"]),
    ("nail-gun", "d/d6/FO4CC_Weapon_Nail_Gun.webp", "3638e5feaebf4963cb01fc53b202dc965cbaf1fc83883e229e8ceda44293ceb4",
     ["Nail Gun"]),
    ("nuka-grenade", "f/f2/Fo4_Nuka_grenade.png", "8e266cc3bd6bea252dcf8caa01c0e4c0bfa96272c724ba81c7f1f0ebbb162671",
     ["Nuka Grenade"]),
    ("nuka-nuke-launcher", "3/30/FO4NW_Nuka-Nuke_launcher.png", "aa23219b11f9e2adb13ac693d2f79ee3db4812ea3967310ecea52c1f4624a327",
     ["Nuka-Nuke Launcher"]),
    ("nuka-quantum-grenade", "3/3f/Nuka_Quantum_grenade.png", "36ebb42699cead0b605fb55e551bbefbd1c0650e8a0430b2f1ced5cf3f406394",
     ["Nuka Quantum Grenade"]),
    ("nuke-mine", "1/12/Nukemine.webp", "d0fed5540af31facf136b8ecf06ba0af393c72091207a454298be000eb243159",
     ["Nuke Mine"]),
    ("old-reliable", "1/12/FO4FH_Old_Reliable.png", "8d34a740dfe3a4742f4bd4447012f9727b419b1af2da645466666ee59cbd4663",
     ["Old Reliable"]),
    ("outcast", "6/6a/FO4CC_Weapon_Solar_Cannon.png", "845044f179fe47a6e401abb0e6d13690c4a3495f0df26713b73f2b8413d86799",
     ["Outcast", "Solar Cannon", "Solar Cannon Mk.II"]),
    ("overseers-guardian", "1/1f/FO4_Weapon_Overseer%27s_Guardian.webp", "966858aa346e53290d1447ac016856f60562ff9ac3b9a986e0f084e49d5abc3c",
     ["Overseer's Guardian"]),
    ("paddle-ball", "c/ce/PaddleBall.png", "44954b6ac3a57bc44fc454dd116703543cd604614a065daa03e0d1abe3419c60",
     ["Paddle Ball"]),
    ("partystarter", "c/c0/Missile_launcher_%28Fallout_4%29.png", "99fa991e198c8542aa04c3d1f7a87f65d48ad3048bd4fa1f02a678f18af6c882",
     ["Death From Above", "Missile Launcher", "Partystarter"]),
    ("persuasion-grenade", "5/56/PersuasionGrenade-NukaWorld.png", "4850fd9d901678c66f5316ce57d1c3533bac448ca4a9b58eabdd695317d04a2a",
     ["Persuasion Grenade"]),
    ("pickmans-blade", "7/76/Pickmans_Blade.png", "4537be1bcc14836bb4ea695bdb63bd35a4666540826fb830e737fb1d23c10c72",
     ["Pickman's Blade"]),
    ("piggy-bank-mine", "e/e3/FO4_Next_Gen_Piggy_Bank_Mine.webp", "ee4125cffa1d3a1406d3a56da8fdcde8567c0e698d6de165801ade73607d4d9a",
     ["Piggy Bank Mine"]),
    ("pint-sized-slasher-knife", "d/dd/F4_PSS_Knife_Trans.png", "ae1ef4067316886d4e1e8287eb0e912935d0308cc261dbbe8f6950e702f0f237",
     ["Pint-Sized Slasher Knife"]),
    ("pipe-bolt-action", "b/b9/Fo4_pipe_bolt-action.png", "1caff88a30b229de523ec4a37367d6fc837d60c1204f88d72420925c79b5a0da",
     ["Pipe Bolt-Action"]),
    ("pipe-gun", "6/6b/Fallout4_pipe_pistol.png", "453c0adb54eb430bfcbaa6ab3b089ee901bedcc3ffc862777fcd802973d5d20d",
     ["Pipe Gun"]),
    ("pipe-revolver", "d/db/Pipe_revolver.png", "02d592b027d432cb073ac61238d1a7d5c43a9b0d4b9f2d8635b590357e165e5b",
     ["Pipe Revolver"]),
    ("plasma-grenade", "d/d9/Plasma_grenade_%28Fallout_4%29.png", "e180baa562e19c7fa0c739657fd14238ff1c9077c569ef7c43d2887b09e2721a",
     ["Plasma Grenade"]),
    ("plasma-gun", "2/21/Fallout4_plasma_pistol.png", "a24f54b194d7c429e10e4ab92609740ea09b08f9ba72f2467a6fe5c9bc240624",
     ["Plasma Gun"]),
    ("plasma-mine", "8/86/Plasmamine.webp", "19bd44919cfbb9fc1ca6d45e0c7326f7ecda9a2f32b4bff314987db60cceb3fb",
     ["Plasma Mine"]),
    ("poisoned-caltrops", "a/a0/Poisoned_caltrops.png", "f27b7f4b099d123f6d185fafc832a868f1d81fb4c199f4d316561d6c084ed33a",
     ["Poisoned Caltrops"]),
    ("pole-hook", "d/d5/Pole_hook.png", "736f2f72cd5e1cfff1559e97092d24c0f266fb174d606967f779ae89b84e2f4d",
     ["Bloodletter", "Pole Hook", "The Fish Catcher"]),
    ("pool-cue", "d/d9/Fallout4_Pool_cue.png", "15e0dc3a0c32bb234c9c01e0007f2465b19847b522ad6cc22fa1907a084fa2ff",
     ["Pool Cue"]),
    ("power-fist", "7/70/Power_fist_%28Fallout_4%29.png", "40c9624b7789fcd0ab7bfa402846dee3a587662cd54267e4c83edf46bd38d8d0",
     ["Power Fist"]),
    ("predator-grenade", "9/90/PredatorGrenade-NukaWorld.png", "78b2c6f049d96529de331ed6f5014ca24f7acc6a829750cd118ac47f34ef92d5",
     ["Predator Grenade"]),
    ("protectrons-gaze", "9/95/Protectron%27s_Gaze.png", "da32575aa590275423cd4962613db344f00f4261afad1b181668d5386b30a018",
     ["Protectron's Gaze"]),
    ("prototype-gauss-rifle", "7/7a/CC_Prototype_Gauss_rifle.png", "c275088e6fb3fc135b99503c74fe412b94fe066cf910a063ba5c559f6bab4c8b",
     ["Prototype Gauss Rifle"]),
    ("pulse-grenade", "0/05/Fallout4_Pulse_grenade.png", "fe2e1f9fb6ec21c1172f16393bed5c379d48fdf8d526790befb9029ea431064f",
     ["Pulse Grenade"]),
    ("pulse-mine", "a/ab/Pulsemine.webp", "abcc6f3f099dec6ea0984b29a6ed9bce6f1e00f6575a96800019180319408904",
     ["Pulse Mine"]),
    ("radium-rifle", "f/fd/FO4FH_Radium_rifle.png", "e901d992d13c50682be3956e72ad286bf0c04ed6f71d5f966e1c87b64cac5cea",
     ["Kiloton Radium Rifle", "Radical Conversion", "Radium Rifle"]),
    ("railway-rifle", "6/6f/Railway_rifle_%28Fallout_4%29.png", "73d168ff4310dd02aafb12f6a76a0200565e1ef88d0d0f4f70ef7f3a1baa3386",
     ["Prototype Railway Rifle", "Railway Rifle"]),
    ("reba", "5/59/Huntingriflefo4.webp", "48a94d79fe0319ea9026774aa902e2bc9a2878467b998c5fd67abc76bfdf22e9",
     ["Reba"]),
    ("reba-ii", "9/92/RebaII.png", "9acb6266ab87191a1b9a42ee989d57374e14fae80bc58759282bc219874d24e5",
     ["Reba II"]),
    ("revolutionary-sword", "5/59/Revolutionary_sword.png", "3f3b40fb331dfb2cb4db04abc4c6b5faa201e8b28a517b8e3ce399ef347c4b05",
     ["Revolutionary Sword"]),
    ("ripper", "3/3e/Ripper_%28Fallout_4%29.png", "e20bfceef820b4fb068d91751156a4057995580c30dc9bd918c762742744e572",
     ["Reckoning", "Ripper", "The Harvester"]),
    ("rockville-slugger", "e/e1/Rockville_Slugger.png", "3e10cc0cdc7c61ec3c4b039adec854f458b647496b341b9376ac0a5d9fa91187",
     ["Rockville Slugger"]),
    ("rolling-pin", "c/c6/Fallout4_Rolling_pin.png", "3161de79945b42c1cc24ba1e6b220adef87de403f15d30773c8494c4edaa0d58",
     ["Rolling Pin"]),
    ("salvaged-assaultron-head", "b/ba/Salvaged_assaultron_head.png", "17f3367ddf2d7af89b7ba837957e0838d449790964205e4b60752d961310dd9d",
     ["Salvaged Assaultron Head"]),
    ("sentinels-plasmacaster", "9/9d/Fallout4_plasma_thrower.png", "fa28f82b77191977e571bfc10c24c2408baa9643855d97eeba164665c6eac11a",
     ["Sentinel's Plasmacaster"]),
    ("shem-drowne-sword", "b/b9/Shem_Drowne_sword.webp", "124d4cf0d8a17dff59836f5adef72a9cc2398fcf15796b6fde732b22263608f8",
     ["Shem Drowne Sword"]),
    ("shishkebab", "5/5d/Shishkebab_%28Fallout_4%29.png", "8d7fdc2ee7a04525393c7fa705509a0ee4db1847dd5a17d7ed2f58e0855ab220",
     ["Shishkebab"]),
    ("silver-sidearm", "6/68/FO4CC_Silver_sidearm.png", "81c0cd9b1e7494a3fc6cc9067846a7d377640557f1f925c6aaa7a01422e84724",
     ["Silver Sidearm"]),
    ("silver-submachine-gun", "a/a2/Silver_submachine_gun.png", "e305285b0d4eb826f1f94eda2a56404b50c665aacb3434f8a16455234ca1d754",
     ["Silver Submachine Gun"]),
    ("sledgehammer", "7/77/Fo4_sledgehammer.png", "0e73117a9ef3909bbc67714b598ee60dd7c15a24989ea939e0a0a97f224e0a5c",
     ["Sledgehammer"]),
    ("smart-fragmentation-grenade", "b/b6/Smart_fragmentation_grenade.png", "8a6737b963d9dba432d01bd1a4268230fb0962f70ce8f0aa98cdda8cb9f509eb",
     ["Smart Fragmentation Grenade"]),
    ("splattercannon", "9/9d/Splattercannon.png", "b497f1debd991562a75eaa995eb7130f3de5d06e55cb43633766f61f4ab0dfd1",
     ["Splattercannon"]),
    ("spray-n-pray", "f/f6/Spray_n_Pray.png", "451cbcdd46793a94738c386e91f7e69e51b6490b25bd60b0f05689e54a7e210a",
     ["Spray n' Pray"]),
    ("steel-sword", "3/3a/Fo4CC_steel_sword.png", "8785a6814c5de46956d12c1071c6a65767942f6c406045e687ffc599a7e4631f",
     ["Steel Sword"]),
    ("submachine-gun", "3/32/FO76_Submachine_gun.png", "4a3de48eae9a4f0b49ca9da5ff0b1b3460ea8f4d73ef75370243538c0685dc72",
     ["Submachine Gun"]),
    ("super-sledge", "b/b4/Super_sledge_%28Fallout_4%29.png", "98817e55a22db4be6da42f568ab494774ac111509d84a3d33b58868291cda480",
     ["Super Sledge"]),
    ("survivors-special", "5/5b/Fallout_4_Survivors_Special.png", "6f84f5399ce0774fe1d11bb05ded8a5e6c6ca46f02386e3e7feccc48b9e83ffc",
     ["Survivor's Special"]),
    ("swatter", "f/f7/Natural_baseball_bat_fo4.png", "098e874466d265c8201aab236670010fd61b138eaabda3812ccb73176c182e74",
     ["Baseball Bat", "Swatter"]),
    ("switchblade", "0/0d/Fo4_switchblade.png", "4ec08a8b9a9e77fb7a5698ca44acc7ac73be0289b94e1636c8db0a42e215bcc3",
     ["Switchblade"]),
    ("sword-of-wonders", "e/e0/Fo4Sword_of_Wonders.png", "3ef3a5be844cf4df57488ea55dcd5c1cedf473b1e9aae8c4c35d08cd2acc5cf6",
     ["Sword of Wonders"]),
    ("syringer", "8/88/Syringer.png", "18b40b8f9a504017e0bd2e94a2424ec2f647053588d195c86899fb1f55f0aa27",
     ["Syringer"]),
    ("tesla-cannon", "e/ee/Fo4CC_Tesla_cannon.png", "aeb55f410c86bd9ff1ef1e34bb27848c8ef373c0c3663f8d68cfc7a28ecfa4b1",
     ["Tesla Cannon"]),
    ("tesla-rifle", "4/42/Tesla_rifle.png", "bda2335ffc341a6e417d1705cb579c1f184265e8fad20ef3b9a172afc25db6bf",
     ["Tesla Rifle"]),
    ("the-gainer", "2/25/The_Gainer.png", "f34b13ac84a4f2965d409791b979a648c3ecd84e8926d1be1c7f3dc411bf565f",
     ["The Gainer"]),
    ("the-problem-solver", "a/ab/FO4NW_The_Problem_Solver.png", "8f22da677c729b5dfa76cccc0fcb408d8f577cfc2cc9e2e1d389a9bbd20617a3",
     ["The Problem Solver"]),
    ("the-striker", "1/10/The_Striker.png", "14aa88214580ba3001f314c3fdf9f0efe34594f523f749c462f4ce5c3624962e",
     ["The Striker"]),
    ("thirst-zapper", "6/6b/Thirst_Zapper.png", "37fb07ea9cbd24f0c3f877737350c8db94669f6db17cbcffcce7221e09523aab",
     ["Thirst Zapper"]),
    ("throatslicer", "1/1b/Fo4DisciplesBlade_HackingBladeMod.png", "5f7f4009373c9a04e5858582785c2074fffdd91cef3efc565505f687d1226e84",
     ["Disciples Blade", "Throatslicer"]),
    ("thunderbolt", "d/db/Thunderbolt.png", "fba717d8f5f5312cce8894c53c02bb1e492b0d42a36b46d1c8b86a4fd13fadcd",
     ["Thunderbolt"]),
    ("tinker-tom-special", "d/db/Tinker_Tom_Special.png", "04106aa9b444f07ee238e67680ac8e1aa5f918364af9bcb88551391eaaab7627",
     ["Tinker Tom Special"]),
    ("tire-iron", "7/7e/Fallout4_Tire_Iron.png", "116709db4c6a2dcc1fad181b81cf5a2aa90fb517e71756c04cae00afd30bccf4",
     ["Tire Iron"]),
    ("triple-barrel-handmade-shotgun", "e/ea/Triple-barrel_handmade_shotgun.png", "4d39fb27034b387de0507f927a587eb8289061661c86554b92dc95807c041412",
     ["Triple-Barrel Handmade Shotgun"]),
    ("ultimatum", "d/d5/FO4CC_Weapon_Ultimatum.webp", "fecf9f525a6f965d7792b08fcb965d8463cf95d576be1766940c56dd38ba4fc8",
     ["Ultimatum"]),
    ("virgils-rifle", "7/74/Virgils_rifle.png", "be422d59d6d2aff13bd6ff0f9d391246714cf306807cb11c979907abbbfca439",
     ["Virgil's Rifle"]),
    ("walking-cane", "7/72/Walking_cane.png", "75f4092d7ef7e29f7f64e5c69d7980259c5cc65f496a9204b4843bcf9de40e1d",
     ["Walking Cane"]),
    ("wastelanders-friend", "2/2a/Fo4_wastelanders_friend.png", "3d3243cc6c0b4ab4d7b38f36dd138aa0533371088dbd52426a099d6b9eff16e4",
     ["Wastelander's Friend"]),
    ("wazer-wifle", "4/40/Fallout_4_Laser_Rifle.png", "ced66f23169174c81c5e2f5e29237c6f50c587935cdfaaa08ca86ef878b07220",
     ["Righteous Authority", "Wazer Wifle"]),
    ("western-revolver", "c/ce/WesternPistol.png", "0383102cbe40c222e12f54ec4218ceb6bd8669b6d481291d2e3943fbe5fa5398",
     ["Western Revolver"]),
    ("zaos-sword", "f/f4/Chinese_officer_sword_%28FO4%29.png", "22bdaec76a7042b4f75480fc247efce4aabe61942e3d2c8aa37e8c9b6e975031",
     ["Chinese Officer Sword", "Zao's sword"]),
    ("zeta-gun", "f/f2/Gamma_gun_%28Fallout_4%29.png", "e6e5d04a8eea479e3acd1ac46462069dadb0d003de04b558be84d2cbae96f2a4",
     ["Gamma Gun", "Zeta Gun"]),
]


def fetch(url, sha256):
    """The file, or None (with a warning) if it can't be had or has changed."""
    run = subprocess.run(["curl", "-fsSL", "--max-time", "120", "-A", "Mozilla/5.0", url],
                         stdout=subprocess.PIPE)
    if run.returncode != 0:
        print(f"fetch-art: warning: could not download {url}", file=sys.stderr)
        return None
    got = hashlib.sha256(run.stdout).hexdigest()
    if got != sha256:
        print(f"fetch-art: warning: {url} has hash {got}, expected {sha256}; left out", file=sys.stderr)
        return None
    return run.stdout


def mask(data, size=None):
    """White, with the picture's brightness (stretched to the full range)
    as its opacity: dark lines drop out, light areas take the color. Made
    to fit size (width, height) if given."""
    from PIL import Image, ImageChops
    Image.MAX_IMAGE_PIXELS = None  # one wiki picture is 12036 x 5100
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    alpha = im.getchannel("A")
    lum = im.convert("L")
    # The darkest and lightest 2% of the visible pixels set the range.
    hist = lum.histogram(mask=alpha.point(lambda a: 255 if a > 128 else 0))
    total = sum(hist)
    lo = hi = 0
    seen = 0
    for v, n in enumerate(hist):
        seen += n
        if seen <= total * 0.02:
            lo = v
        if seen <= total * 0.98:
            hi = v
    hi = max(hi, lo + 1)
    level = lum.point(lambda v: round(255 * min(1.0, max(0.0, (v - lo) / (hi - lo))) ** 0.8))
    out = Image.merge("LA", (Image.new("L", im.size, 255), ImageChops.multiply(level, alpha)))
    if size:
        out.thumbnail(size, Image.LANCZOS)
    return out


def fetch_bundle():
    url, sha256 = BUNDLE
    data = fetch(url, sha256)
    if data is None:
        return 1
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(OUT, filter="data")
    # The bundle's times are 0 (1970), which a zip can't hold: make them now.
    count = 0
    for root, _, files in os.walk(OUT):
        for f in files:
            os.utime(os.path.join(root, f))
            count += 1
    print(f"fetch-art: {count} files in {os.path.relpath(OUT)}")
    return 0


def write_bundle(path):
    """art/ as a .tar.gz, the same bytes for the same pictures."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for root, dirs, files in os.walk(OUT):
            dirs.sort()
            for f in sorted(files):
                full = os.path.join(root, f)
                info = tar.gettarinfo(full, os.path.relpath(full, OUT))
                info.mtime, info.uid, info.gid, info.uname, info.gname, info.mode = 0, 0, 0, "", "", 0o644
                with open(full, "rb") as fh:
                    tar.addfile(info, fh)
    with open(path, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as gz:
        gz.write(raw.getvalue())
    with open(path, "rb") as fh:
        print(f"fetch-art: {path}: sha256 {hashlib.sha256(fh.read()).hexdigest()}")


def save(image, name):
    dest = os.path.normpath(os.path.join(OUT, name))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    image.save(dest, optimize=True)


def from_sources(bundle):
    shutil.rmtree(OUT, ignore_errors=True)
    missing = 0
    for name, (path, sha256) in ART.items():
        data = fetch(f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{path}", sha256)
        if data is None:
            missing += 1
            continue
        save(mask(data), name)
    names = {}
    for slug, path, sha256, weapons in WEAPONS:
        data = fetch(WIKI + path, sha256)
        if data is None:
            missing += 1
            continue
        save(mask(data, (640, 320)), f"weapons/{slug}.png")
        names[slug] = weapons
    with open(os.path.join(OUT, "weapons.json"), "w", encoding="utf-8") as fh:
        json.dump(names, fh, indent=1, ensure_ascii=False)
    print(f"fetch-art: {len(ART) + len(WEAPONS) - missing} pictures in {os.path.relpath(OUT)}"
          + (f", {missing} left out (see the warnings)" if missing else ""))
    if missing:
        print("fetch-art: no bundle with pictures missing", file=sys.stderr)
        return 1
    write_bundle(bundle)
    return 0


def main():
    if sys.argv[1:2] == ["--from-sources"]:
        return from_sources(sys.argv[2] if len(sys.argv) > 2 else "pipboy-art.tar.gz")
    return fetch_bundle()


if __name__ == "__main__":
    sys.exit(main())

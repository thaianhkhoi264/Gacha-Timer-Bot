There are a few pages on a website that I need data to be parsed from. You will need to go to the website yourself to understand the structure of that website.

The databases should be in /data/JP_Data/

The first one is from this website:
https://gametora.com/umamusume/gacha/history?server=en&type=char&year=2025

Near the top of the website, there should be 3 selectable categories:

Server: Global, JP, KR, TW
Year: All, 2021-2025 (JP ONLY)/2025 (GLOBAL ONLY)/2022-2025(KR/TW ONLY)
Type: Characters, Support, All

This website contains the Event Images and Event banner images for both the Global version and the Japanese version of the game. IGNORE THE KR/TW SERVERS.

For the Japanese server, so everything done *should* be in the JP Server, All in both Year and Type option on the website
In this first step, the code should be linking and saving each event/banner in the database by Type, ID, Description, Characters/Cards, and link

The banner Type is below the image, it should be either "Character Gacha" or "Support Card Gacha", save them as Character/Support in the database
The  ID is in the *IMAGE NAME* in the link, for example, if an image for an event has this link: https://gametora.com/images/umamusume/gacha/img_bnr_gacha_30380.png then the banner ID is 30380. DO NOT SAVE THE IMAGE ITSELF IN THIS PART
The description is empty most of the time, but in some cases, some events has this below the "Banner Type" spot: "⬆️ 3⭐ — 4.5% rate", which then needed to be saved in the Description.
Each Banner can have from 1 to an unknown number of Character/Cards, each with their own link, so the character and the link should be dynamic if possible

For example:

Event with ID 30336 has 1 Character, "Verxina", and the link for that character can be found at "https://gametora.com/umamusume/characters/109001-verxina". This link can be found by hovering over that character's name in the event, and the link is in "Open the details page" link.

Event with ID 30332 has 17 Characters, Each of them with the link as well.

When you do this, create 2 other databases. One for characters and another for support cards.

For the Character Database, There should be a character ID, Character Name and Link.

All of them can be found from the link itself. In the example on top, The character "Verxina" has the ID "109001" and the link is "https://gametora.com/umamusume/characters/109001-verxina"

Some characters can have the same name but with different versions, so keep that in mind. For example:

ID: 103001 Name: Rice Shower Link: https://gametora.com/umamusume/characters/103001-rice-shower
ID: 103002 Name: Rice Shower (Halloween) Link: https://gametora.com/umamusume/characters/103002-rice-shower
ID: 103003 Name: Rice Shower (Great Food Festival) Link: https://gametora.com/umamusume/characters/103003-rice-shower

Same thing for the Support Database, but in this case, two Support cards can have the EXACT same name (e.g. Mihono Bourbon (SSR WIT)), but as long as the ID and Link are different, we can keep them both.

That's the end of Step 1.

For step 2, we change the the server to Global, keep Year and Type to All.

Now, we only do two things, We look for an event ID from each event similar to the first step, and then we SAVE the image, and in another database, or use the one what we already have if you think that it is better that way, we just link the event ID with the image file name.
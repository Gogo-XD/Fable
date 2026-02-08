# Timeline - Ancient
World: Test World 2
Generated at (UTC): 2026-02-08T08:27:29.565356+00:00
World description: N/A

Total markers: 4

- marker `28914988-fe55-4454-9e71-cb8e3fa37c07` | The Coronation at Sunspire (1189) | when=1189 | kind=explicit | placement=placed
  summary: The coronation of Queen Mirelle Valedorn took place following the death of King Oren Valedorn. Prince Caelan was named heir and House Thorn swore fealty.
  operations:
  - entity_create | target_kind=entity | target_id=3731b599-ff6f-47c6-88c7-2c143a0b4810 | op_id=430b7067-7cf0-40d5-9b86-819b2aa481cf
    payload: {"name": "King Oren Valedorn"}
  - entity_create | target_kind=entity | target_id=ba1b2e19-c557-49af-aa5c-4a95b4810313 | op_id=f1c5a1d1-f73d-46e6-87c1-768cfcef3d2a
    payload: {"name": "Prince Caelan"}
  - entity_create | target_kind=entity | target_id=c6907738-9125-424f-b9ed-e73e9c1a12e7 | op_id=bef73623-6204-486c-afd9-c1d783cd4911
    payload: {"name": "House Thorn"}
  - relation_create | target_kind=relation | target_id=7e6eb075-d841-4939-b068-d03ddba3c5a6 | op_id=c8e53086-735e-4659-baa5-e63487ffb698
    payload: {"source_entity_id": "d83c4db8-cc20-4443-85af-2f57aaa625e2", "target_entity_id": "3731b599-ff6f-47c6-88c7-2c143a0b4810", "type": "successor"}
  - relation_create | target_kind=relation | target_id=a49fa9c8-bd94-476d-b5f7-77e2245bd5fb | op_id=dcd5a645-f6fa-4fc1-88dc-62552a3675a0
    payload: {"source_entity_id": "ba1b2e19-c557-49af-aa5c-4a95b4810313", "target_entity_id": "d83c4db8-cc20-4443-85af-2f57aaa625e2", "type": "heir"}
  - relation_create | target_kind=relation | target_id=77632c4e-b2cb-4a0c-8985-569d3bc2f85b | op_id=2d1ddec3-8a18-4134-898b-066cf12c517b
    payload: {"source_entity_id": "2985ab82-2d05-4d51-b088-d2db883aef60", "target_entity_id": "e8e0eb86-06c3-4c08-8a18-a35021b243d1", "type": "commander_of"}
  - relation_create | target_kind=relation | target_id=51e8bcc9-5871-4882-8889-28dd20f4ae6c | op_id=2a1b171f-fc65-4b97-8cf4-7505c1ac8110
    payload: {"source_entity_id": "c6907738-9125-424f-b9ed-e73e9c1a12e7", "target_entity_id": "d83c4db8-cc20-4443-85af-2f57aaa625e2", "type": "allegiance"}
- marker `0e135ba4-75d7-4125-b98a-3e25386fd8ac` | Pact of Lantern and Crown | when=1194 | kind=explicit | placement=placed
  summary: The Order of the Ash Lantern signed a defensive pact with Queen Mirelle.
  operations:
  - entity_create | target_kind=entity | target_id=dc5011b5-b348-4f17-a9fe-219a7c96a527 | op_id=e7f776db-2884-4901-a423-a006b8a4aac9
    payload: {"name": "Order of the Ash Lantern"}
  - entity_create | target_kind=entity | target_id=d83c4db8-cc20-4443-85af-2f57aaa625e2 | op_id=18f1bccc-72ed-4313-862a-6c5eeaf7df70
    payload: {"name": "Queen Mirelle"}
  - entity_create | target_kind=entity | target_id=68bdc216-f4f8-4746-b5d6-8e5d8ceb9baf | op_id=86044361-64cf-4849-811b-3ff7d2d2b0ef
    payload: {"name": "High Warden Branik"}
  - entity_create | target_kind=entity | target_id=fd7a7d87-b6ff-4285-993d-fc616fee178d | op_id=369fcf9c-7180-4b60-9061-f35efc6754a7
    payload: {"name": "Ember Monastery"}
  - entity_create | target_kind=entity | target_id=a2aa128c-e07c-41f8-a4e3-13e7d41f0553 | op_id=1dd21531-d959-4c2d-bb5e-b077ad501c0a
    payload: {"name": "defensive pact"}
  - relation_create | target_kind=relation | target_id=465da17c-0257-491a-8e02-3c91ec3b17a1 | op_id=3d3f183b-751f-4cf6-8c03-e31b8294add6
    payload: {"source_entity_id": "dc5011b5-b348-4f17-a9fe-219a7c96a527", "target_entity_id": "d83c4db8-cc20-4443-85af-2f57aaa625e2", "type": "alliance"}
  - relation_create | target_kind=relation | target_id=c51ac88a-542f-4650-a4d9-bea35447fada | op_id=af5e4330-e84c-42fe-bd75-3b58c8441cbd
    payload: {"source_entity_id": "68bdc216-f4f8-4746-b5d6-8e5d8ceb9baf", "target_entity_id": "dc5011b5-b348-4f17-a9fe-219a7c96a527", "type": "leadership"}
  - relation_create | target_kind=relation | target_id=0fb93807-a3c4-444b-95b2-adf0d037ec8a | op_id=5e35010b-7248-46a3-aaa4-7d72c70f4a0a
    payload: {"source_entity_id": "dc5011b5-b348-4f17-a9fe-219a7c96a527", "target_entity_id": "fd7a7d87-b6ff-4285-993d-fc616fee178d", "type": "stewardship"}
- marker `dcee6ad2-cefd-4076-ac14-17971750b376` | Discovery Beneath Blackmere | when=1198 | kind=explicit | placement=placed
  summary: Archmage Selene Voss discovered the Dawnforge Lens beneath Lake Blackmere and claimed it against the Iron Covenant.
  operations:
  - entity_create | target_kind=entity | target_id=2d31f3a1-f63e-471a-b03c-67aefbfacef6 | op_id=468b1a13-c79c-41be-b4ba-827dc548c417
    payload: {"name": "Archmage Selene Voss"}
  - entity_create | target_kind=entity | target_id=e5558e56-fa22-4cdd-81d5-41d5cdbbeb95 | op_id=6e587dfb-4278-4e20-bfe2-51f339fb8a3c
    payload: {"name": "Dawnforge Lens"}
  - entity_create | target_kind=entity | target_id=8df701a8-c0cc-4d95-b28e-29843e4f863f | op_id=0b0f073a-92ac-4786-bf4b-3850227f70e6
    payload: {"name": "Iron Covenant"}
  - entity_create | target_kind=entity | target_id=73d296ef-356c-490c-b537-ed56d2964744 | op_id=1a1074eb-503f-488d-99a3-091bc0ec6b91
    payload: {"name": "Lake Blackmere"}
  - entity_create | target_kind=entity | target_id=4d317f61-1a36-485b-a0a4-bc4272e4b63e | op_id=6e7331e4-6467-49d7-805c-f9c57bf8b2fd
    payload: {"name": "Sunspire"}
  - relation_create | target_kind=relation | target_id=434c1d06-8501-4bc9-981f-83611251e634 | op_id=6b4248e9-5fc1-483d-b4be-d9ff25bde15e
    payload: {"source_entity_id": "2d31f3a1-f63e-471a-b03c-67aefbfacef6", "target_entity_id": "e5558e56-fa22-4cdd-81d5-41d5cdbbeb95", "type": "discovered"}
  - relation_create | target_kind=relation | target_id=f1a00824-f345-41f5-ba8c-20d5ce379412 | op_id=6a7477a5-2d6e-43c9-af5b-515ecc789625
    payload: {"source_entity_id": "8df701a8-c0cc-4d95-b28e-29843e4f863f", "target_entity_id": "e5558e56-fa22-4cdd-81d5-41d5cdbbeb95", "type": "claimed"}
  - relation_create | target_kind=relation | target_id=d3cf3558-da72-4cc8-9361-83f7c211d375 | op_id=5ec30ebc-f00e-4349-ba39-83f4dd4a2c79
    payload: {"source_entity_id": "2d31f3a1-f63e-471a-b03c-67aefbfacef6", "target_entity_id": "4d317f61-1a36-485b-a0a4-bc4272e4b63e", "type": "moved"}
  - relation_create | target_kind=relation | target_id=9e2823f8-3da2-44de-9bd1-d6c85c3462cb | op_id=f938050b-893b-481a-ab44-7332f0a6850e
    payload: {"source_entity_id": "e5558e56-fa22-4cdd-81d5-41d5cdbbeb95", "target_entity_id": "73d296ef-356c-490c-b537-ed56d2964744", "type": "location_of_discovery"}
- marker `8d24cd47-fcf3-49be-bc70-4589362cdc78` | In the Ashen Years | when=sort_key=1198.375 | kind=semantic | placement=placed
  summary: Prince Caelan abandoned his title as heir and founded the Gray Banner Company, while Selene Voss disappeared.
  operations:
  - entity_patch | target_kind=entity | target_id=ba1b2e19-c557-49af-aa5c-4a95b4810313 | op_id=c1604420-23a6-49aa-a5f3-de15940b364e
    payload: {"context": "Prince Caelan abandoned his title as heir.", "name": "Prince Caelan", "summary": "Abandoned heir title."}
  - entity_create | target_kind=entity | target_id=b3881a2a-b9d1-4314-82ab-8865c26824a3 | op_id=067cc2e5-d608-44d5-8cbf-3d99ba7c9817
    payload: {"name": "Gray Banner Company"}
  - entity_create | target_kind=entity | target_id=47d817d5-7d68-43f2-87fd-a237601b6e1d | op_id=5d91de2f-94b0-40ff-9c75-e68db1ca43e1
    payload: {"name": "Elara Thorn"}
  - relation_create | target_kind=relation | target_id=6ea55b28-bdf7-43ad-8bb0-ea93aced8996 | op_id=119ef84c-6e82-489f-ab7a-f51904b840db
    payload: {"source_entity_id": "ba1b2e19-c557-49af-aa5c-4a95b4810313", "target_entity_id": "b3881a2a-b9d1-4314-82ab-8865c26824a3", "type": "founder"}
  - relation_create | target_kind=relation | target_id=d23c09a7-aa06-4841-9621-6b87b336adba | op_id=76c551d2-b728-44ca-9214-a082babfd8ad
    payload: {"source_entity_id": "47d817d5-7d68-43f2-87fd-a237601b6e1d", "target_entity_id": "b3881a2a-b9d1-4314-82ab-8865c26824a3", "type": "patron"}
  - entity_patch | target_kind=entity | target_id=2d31f3a1-f63e-471a-b03c-67aefbfacef6 | op_id=6b9b87dd-da8d-4173-a4cc-d4195e0b8366
    payload: {"context": "Selene Voss left a final note and disappeared.", "name": "Archmage Selene Voss", "summary": "Disappeared after leaving a warning note."}

Total operations in slot: 30

# Timeline - Present
World: Test World 3
Generated at (UTC): 2026-02-08T10:24:57.449485+00:00
World description: N/A

Total markers: 1

- marker `200e23f5-d2c0-4c98-bd54-00b65a82d757` | Siege of Graywall Begins | when=1203 | kind=explicit | placement=placed
  summary: The Iron Covenant under Warlord Dagan Korr begins siege on Graywall in 1203; supply lines from Sunspire cut at Hollow Ford. Prince Caelan leads unsuccessful relief attempt.
  operations:
  - entity_create | target_kind=entity | target_id=c1919688-093c-40e2-8adf-777cf87abb3b | op_id=4fcd210a-877f-45b7-94a1-b22865813177
    payload: {"context": "The Iron Covenant is a militant group that marched under the command of Warlord Dagan Korr to besiege Graywall.", "name": "Iron Covenant", "subtype": "military faction", "summary": "A military faction led by Warlord Dagan Korr.", "type": "organization"}
  - entity_create | target_kind=entity | target_id=534a23c2-db9e-4990-a663-7a46aebc0b46 | op_id=14cf62c5-00d6-48e6-99a1-1e74f9e64534
    payload: {"context": "Warlord Dagan Korr led the Iron Covenant forces in the siege of the city of Graywall.", "name": "Warlord Dagan Korr", "subtype": "military leader", "summary": "Commander of the Iron Covenant during the Siege of Graywall.", "type": "character"}
  - entity_create | target_kind=entity | target_id=3925038d-0406-4d08-8d17-bf1d6f8b123b | op_id=f3beb6b8-767e-4f8a-ac1c-c229c46c239c
    payload: {"context": "Sunspire was the origin point of the supply routes to Graywall that were severed at the Hollow Ford by the besieging forces.", "name": "Sunspire", "subtype": "settlement", "summary": "Origin of supply lines cut during the siege.", "type": "location"}
  - entity_create | target_kind=entity | target_id=34e7fca1-245b-4e5e-bc8b-472967ecd633 | op_id=9eff3961-46d2-40dc-b73e-13128be2a48a
    payload: {"context": "Hollow Ford is a strategic location where the Iron Covenant cut off supply lines coming from Sunspire to Graywall.", "name": "Hollow Ford", "subtype": "strategic crossing", "summary": "A strategic crossing where supply lines to Graywall were cut.", "ty...<truncated>
  - entity_create | target_kind=entity | target_id=1b0f50f8-3ff8-400f-b51d-4f231fe7b40b | op_id=e544a687-26db-447b-94b4-2882e7072ef8
    payload: {"context": "Prince Caelan is a royal figure from Graywall who commanded a relief army attempting to lift the siege but was unsuccessful.", "name": "Prince Caelan", "subtype": "military leader", "summary": "Prince of Graywall who led a relief host to break the sieg...<truncated>
  - relation_create | target_kind=relation | target_id=aee8c903-c0d7-4c1c-88bc-b654886f9dea | op_id=4ab5b880-21c8-489a-a889-baa6525d4bab
    payload: {"context": "Warlord Dagan Korr commanded the Iron Covenant during the siege of Graywall.", "source_entity_id": "c1919688-093c-40e2-8adf-777cf87abb3b", "target_entity_id": "534a23c2-db9e-4990-a663-7a46aebc0b46", "type": "led_by"}
  - relation_create | target_kind=relation | target_id=4de9de09-8db2-4092-8a86-4ba59a786fd8 | op_id=2f7cf43d-2d6f-4b14-9625-5c6d0921c74a
    payload: {"context": "The Iron Covenant besieged the city of Graywall.", "source_entity_id": "c1919688-093c-40e2-8adf-777cf87abb3b", "target_entity_id": "2f8c3c70-5b0d-4419-a684-d1348818a0c3", "type": "besieged"}
  - relation_create | target_kind=relation | target_id=8d989513-c625-4928-b854-3304666e200f | op_id=7c55edd4-4de3-4d29-8826-6706f3ba3aa4
    payload: {"context": "Warlord Dagan Korr led forces to besiege Graywall.", "source_entity_id": "534a23c2-db9e-4990-a663-7a46aebc0b46", "target_entity_id": "2f8c3c70-5b0d-4419-a684-d1348818a0c3", "type": "besieged"}
  - relation_create | target_kind=relation | target_id=d2cde1a6-9bf5-4631-bc5c-b7a289c81236 | op_id=d7c559a6-2315-47a1-95e9-b12ebc17d369
    payload: {"context": "Iron Covenant forces cut the supply lines from Sunspire to Graywall at Hollow Ford.", "source_entity_id": "c1919688-093c-40e2-8adf-777cf87abb3b", "target_entity_id": "3925038d-0406-4d08-8d17-bf1d6f8b123b", "type": "cut_supply_lines_from"}
  - relation_create | target_kind=relation | target_id=c43b6ea8-7eef-4ee7-8166-c948d38ac2d8 | op_id=5bc25a3f-e9cb-446c-b3e5-1729a8496bae
    payload: {"context": "Warlord Dagan Korr's forces controlled Hollow Ford to cut off supplies.", "source_entity_id": "534a23c2-db9e-4990-a663-7a46aebc0b46", "target_entity_id": "34e7fca1-245b-4e5e-bc8b-472967ecd633", "type": "controlled_location"}
  - relation_create | target_kind=relation | target_id=f13e19cd-1169-46c2-807f-123f894ad49c | op_id=68594e10-2d13-4dcf-b683-601e1e4c55ea
    payload: {"context": "Prince Caelan led a relief host attempting to break the siege at Graywall.", "source_entity_id": "1b0f50f8-3ff8-400f-b51d-4f231fe7b40b", "target_entity_id": "2f8c3c70-5b0d-4419-a684-d1348818a0c3", "type": "defended"}

Total operations in slot: 11

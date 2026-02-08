# Timeline - Ancient
World: Test World 3
Generated at (UTC): 2026-02-08T10:24:57.449346+00:00
World description: N/A

Total markers: 1

- marker `e4d53aac-b867-497c-82e8-7bb3810b5044` | Famine | when=sort_key=1.0 | kind=semantic | placement=placed
  summary: A blight led to ruined harvests and food riots in Valedorn, with Captain Ilya Thorn intervening.
  operations:
  - entity_create | target_kind=entity | target_id=7492fcef-b9d1-4890-bd14-610108f5be73 | op_id=358f0bbe-c4c2-4e37-b74d-994a0519ac56
    payload: {"name": "Valedorn"}
  - entity_create | target_kind=entity | target_id=2f8c3c70-5b0d-4419-a684-d1348818a0c3 | op_id=f0e85bef-0543-4bdc-a215-7fd2c98126e1
    payload: {"name": "Graywall"}
  - entity_create | target_kind=entity | target_id=228adf22-d2c4-4638-951c-e72197473c36 | op_id=0a0d0fc3-8dce-4dc3-80f4-174acc86344b
    payload: {"name": "Salt March"}
  - entity_create | target_kind=entity | target_id=1d47f9d6-9228-43e8-8695-97a778e071dc | op_id=c5a0ec38-8b42-49b5-a20d-e9c7007e3337
    payload: {"name": "Captain Ilya Thorn"}
  - entity_create | target_kind=entity | target_id=50bd4b48-d8d1-48bc-a0af-974e34d02ae4 | op_id=3312291e-8672-42b9-aee0-e950276b4cbf
    payload: {"name": "royal treasury"}
  - relation_create | target_kind=relation | target_id=76dfb08c-5ce5-4346-aec8-45b18c607030 | op_id=9012a4f9-92af-42cf-8923-04f47fcaca71
    payload: {"source_entity_id": "7492fcef-b9d1-4890-bd14-610108f5be73", "target_entity_id": "2f8c3c70-5b0d-4419-a684-d1348818a0c3", "type": "location_contains"}
  - relation_create | target_kind=relation | target_id=78c76695-54c2-48ca-ae93-12e2ed98994c | op_id=b0d4e6e6-b4e9-4b02-9055-64abe4e58046
    payload: {"source_entity_id": "7492fcef-b9d1-4890-bd14-610108f5be73", "target_entity_id": "228adf22-d2c4-4638-951c-e72197473c36", "type": "location_contains"}
  - relation_create | target_kind=relation | target_id=7c9cbbf4-8656-408c-af68-a8fec612445a | op_id=682b5e59-a1e3-4bcb-a48a-47b8fef03023
    payload: {"source_entity_id": "1d47f9d6-9228-43e8-8695-97a778e071dc", "target_entity_id": "50bd4b48-d8d1-48bc-a0af-974e34d02ae4", "type": "tension_with"}

Total operations in slot: 8

# Timeline - Present
World: Test World 2
Generated at (UTC): 2026-02-08T08:27:29.565669+00:00
World description: N/A

Total markers: 5

- marker `e7b051ef-74a3-4d64-bc72-65403e773bcd` | Promotion of Captain Ilya (1206) | when=1206 | kind=explicit | placement=placed
  summary: Captain Ilya Thorn was promoted to Major General by the Prince of Graywall after her actions during the Red Wheat Blight and received the medal of honour.
  operations:
  - entity_patch | target_kind=entity | target_id=2985ab82-2d05-4d51-b088-d2db883aef60 | op_id=884e1b2a-9588-459d-8dba-068de74d2719
    payload: {"context": "Promoted to Major General following actions in the Red Wheat Blight and awarded the medal of honour.", "name": "Captain Ilya Thorn", "summary": "Promotion and Honour awarded."}
- marker `ed8e50f7-f825-4157-8d73-5e69eda4cbf2` | After Graywall, the Crown Fractures | when=1206 | kind=explicit | placement=placed
  summary: Queen Mirelle dismissed Chancellor Varro Pell for negligence, and rumors surfaced about his secret correspondence with Warlord Dagan Korr. The Order of the Ash Lantern withdrew from the court.
  operations:
  - entity_create | target_kind=entity | target_id=609111f5-ec50-4b4a-b194-5462952d1c5d | op_id=8c611952-c00e-4b0d-8365-8531c4870280
    payload: {"aliases": [], "context": "Varro Pell was dismissed for negligence following the fall of Graywall, and rumors suggest he secretly corresponded with Warlord Dagan Korr.", "name": "Chancellor Varro Pell", "subtype": null, "summary": "A chancellor dismissed by Queen ...<truncated>
  - relation_create | target_kind=relation | target_id=8c80fc25-3c82-4aa2-85de-94449dad467e | op_id=c5ff5c3b-aadc-49b8-83e0-fdd87d079b45
    payload: {"context": "Queen Mirelle dismissed Chancellor Varro Pell for negligence after Graywall's fall.", "source_entity_id": "d83c4db8-cc20-4443-85af-2f57aaa625e2", "target_entity_id": "609111f5-ec50-4b4a-b194-5462952d1c5d", "type": "dismissed"}
  - relation_create | target_kind=relation | target_id=1e956276-0eba-4ab8-9edd-e8563481bc86 | op_id=178bbef0-0c3a-4388-ae5a-01d5a6dcf880
    payload: {"context": "Rumors spread that Chancellor Varro Pell was secretly corresponding with Warlord Dagan Korr.", "source_entity_id": "609111f5-ec50-4b4a-b194-5462952d1c5d", "target_entity_id": "7c0f75eb-a11e-4250-81d6-94bdac0c13cb", "type": "secret_correspondence"}
  - relation_create | target_kind=relation | target_id=cf428b86-c7e1-4f98-ae48-a075133ddece | op_id=3a6d7614-8879-4457-86d8-7884fc38be3f
    payload: {"context": "The Order of the Ash Lantern withdrew from the court and returned to the Ember Monastery.", "source_entity_id": "dc5011b5-b348-4f17-a9fe-219a7c96a527", "target_entity_id": "fd7a7d87-b6ff-4285-993d-fc616fee178d", "type": "withdrawal"}
- marker `1d67e64b-1c50-4d1c-9102-852f8b248698` | Reopening of Frostpass | when=1208 | kind=explicit | placement=placed
  summary: Elara Thorn negotiated with the Stoneclan to reopen Frostpass, restoring trade and political influence for House Thorn.
  operations:
  - relation_create | target_kind=relation | target_id=f7133dea-031e-4045-bfd9-568dceb77a72 | op_id=d87dca0b-d972-4283-9be1-fe5540386c6f
    payload: {"source_entity_id": "47d817d5-7d68-43f2-87fd-a237601b6e1d", "target_entity_id": "27b1659d-21d3-4b61-b1dc-205fc64173e6", "type": "negotiation"}
  - relation_create | target_kind=relation | target_id=9220ef7a-0559-4221-9f33-6a09643ed848 | op_id=67fc62b0-ef57-49b1-a751-c15a88b02d7b
    payload: {"source_entity_id": "a971c7d0-e30a-4a96-bfa4-6f11f27b6e75", "target_entity_id": "13431b5b-9aae-4992-a3fb-227ac02d5e0c", "type": "trade_route"}
  - relation_create | target_kind=relation | target_id=b8addc86-adc0-4127-ae37-e7436d768f43 | op_id=6952b337-468d-44ef-a72e-5314a25179bf
    payload: {"source_entity_id": "c6907738-9125-424f-b9ed-e73e9c1a12e7", "target_entity_id": "d83c4db8-cc20-4443-85af-2f57aaa625e2", "type": "political_influence"}
- marker `2d2f4cff-77c9-4f03-9dae-43a1f7ed9958` | Treaty of Three Embers | when=1210 | kind=explicit | placement=placed
  summary: Formal agreement ending hostilities and establishing neutral zones.
  operations:
  - entity_create | target_kind=entity | target_id=2d5832b5-a76f-40fc-aa71-f57b3d24d032 | op_id=6d0daf95-fec3-4cb9-8088-1d3256852075
    payload: {"name": "Treaty of Three Embers"}
  - entity_create | target_kind=entity | target_id=7c0f75eb-a11e-4250-81d6-94bdac0c13cb | op_id=89326338-94f9-44d9-a6b5-a43d39e5ad05
    payload: {"name": "Dagan Korr"}
  - relation_create | target_kind=relation | target_id=33c703f7-6a4b-4431-bb92-988c1ab1cdb8 | op_id=823cc883-b158-4005-bb10-b875ee2e5111
    payload: {"source_entity_id": "2d5832b5-a76f-40fc-aa71-f57b3d24d032", "target_entity_id": "fd7a7d87-b6ff-4285-993d-fc616fee178d", "type": "location_association"}
  - relation_create | target_kind=relation | target_id=03d1c73d-b872-4dc7-818e-154b16d28819 | op_id=a3e533fd-8d9f-489c-a02c-42472bbbf661
    payload: {"source_entity_id": "2d5832b5-a76f-40fc-aa71-f57b3d24d032", "target_entity_id": "13431b5b-9aae-4992-a3fb-227ac02d5e0c", "type": "signatory"}
  - relation_create | target_kind=relation | target_id=7c50cc77-bff1-4a2f-932e-d5f476d48970 | op_id=d1ecfb1d-8b34-4b3e-a7ca-35dc829d01fa
    payload: {"source_entity_id": "2d5832b5-a76f-40fc-aa71-f57b3d24d032", "target_entity_id": "8df701a8-c0cc-4d95-b28e-29843e4f863f", "type": "signatory"}
  - relation_create | target_kind=relation | target_id=c1f37146-545c-4bee-ac2f-40328d5d90c8 | op_id=71a16fdc-390a-4f5c-beb5-34fcc8a799b6
    payload: {"source_entity_id": "2d5832b5-a76f-40fc-aa71-f57b3d24d032", "target_entity_id": "dc5011b5-b348-4f17-a9fe-219a7c96a527", "type": "signatory"}
  - relation_create | target_kind=relation | target_id=b8ffb1d9-5144-43eb-9ab5-4100bee6f3d2 | op_id=eac1864d-ccdf-401d-8ec2-781430fd92b0
    payload: {"source_entity_id": "13431b5b-9aae-4992-a3fb-227ac02d5e0c", "target_entity_id": "e8e0eb86-06c3-4c08-8a18-a35021b243d1", "type": "neutral_zone_establishment"}
  - relation_create | target_kind=relation | target_id=7aca3a01-39b8-4d97-9bd8-5facc2b55e45 | op_id=68ad9262-c179-42f2-8e69-b051963997ed
    payload: {"source_entity_id": "7c0f75eb-a11e-4250-81d6-94bdac0c13cb", "target_entity_id": "d83c4db8-cc20-4443-85af-2f57aaa625e2", "type": "recognition"}
- marker `2e0f03e7-36d0-4de0-96c7-5bcef6aa8459` | The Silence Winter | when=sort_key=1211.0 | kind=semantic | placement=placed
  summary: A peculiar winter marked by strange natural and supernatural occurrences.
  operations:
  - entity_create | target_kind=entity | target_id=5127fdc6-8739-4298-8f75-37edad443757 | op_id=1480885f-c43c-4777-9a40-2b9656863ceb
    payload: {"context": "The Silence Winter is notable for its eerie events, including the absence of birds and the mysterious ringing of temple bells.", "name": "The Silence Winter", "summary": "A winter during which no birds crossed the northern sky and temple bells rang wit...<truncated>
  - entity_create | target_kind=entity | target_id=1a0ab3d3-3eb3-4dd3-8e3b-1414a898bf34 | op_id=1817779f-e128-43b7-beba-b5cc2095538f
    payload: {"context": "The Star Vault is located beneath Sunspire and is used to store important and potentially dangerous items.", "name": "Star Vault", "summary": "A secure location beneath Sunspire."}
  - relation_create | target_kind=relation | target_id=6cdc6f58-754e-45a9-a589-2a579a05788e | op_id=e8577311-05e3-4451-96d3-a4598f04f71f
    payload: {"context": "Selene Voss declared the Dawnforge Lens unstable during the Silence Winter.", "source_entity_id": "2d31f3a1-f63e-471a-b03c-67aefbfacef6", "target_entity_id": "e5558e56-fa22-4cdd-81d5-41d5cdbbeb95", "type": "declared_unstable"}
  - relation_create | target_kind=relation | target_id=fc9de809-bc7b-4c75-9110-3cb2c98f38aa | op_id=02c84809-bd31-43e3-a2fa-719e7efd8e57
    payload: {"context": "The Dawnforge Lens was sealed inside the Star Vault to prevent its instability from causing harm.", "source_entity_id": "e5558e56-fa22-4cdd-81d5-41d5cdbbeb95", "target_entity_id": "1a0ab3d3-3eb3-4dd3-8e3b-1414a898bf34", "type": "sealed_inside"}
  - relation_create | target_kind=relation | target_id=bb70b612-a2d7-4f4b-83f7-410ef8d831c8 | op_id=9683fb30-da5e-4782-8296-cbd8b210ac35
    payload: {"context": "The Star Vault is a location beneath Sunspire.", "source_entity_id": "1a0ab3d3-3eb3-4dd3-8e3b-1414a898bf34", "target_entity_id": "4d317f61-1a36-485b-a0a4-bc4272e4b63e", "type": "located_beneath"}

Total operations in slot: 21

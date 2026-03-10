import subprocess
from pathlib import Path
import argparse

out_dir = Path("docs/architecture/diagrams")
out_dir.mkdir(parents=True, exist_ok=True)

# ==========================================
# 1. MCD (Merise Conceptual Model)
# ==========================================
mcd_dot = """
graph MCD {
    rankdir=LR;
    node [fontname="Helvetica,Arial,sans-serif", fontsize=10];
    edge [fontname="Helvetica,Arial,sans-serif", fontsize=9];

    // Entities
    node [shape=record, style=filled, fillcolor="#E3E8EE"];
    SOURCE_SYSTEM [label="{SOURCE_SYSTEM|id_source\\nname\\nsource_type\\ndescription\\nowner_name\\nlegal_basis\\ncontains_personal_data\\nretention_days\\nis_active}"];
    INGESTION_RUN [label="{INGESTION_RUN|id_ingestion\\nstarted_at\\nfinished_at\\nstatus\\ntrigger_mode\\nraw_object_count\\nraw_record_count\\nlog_message}"];
    RAW_OBJECT [label="{RAW_OBJECT|id_raw_object\\nexternal_ref\\nobject_type\\nstorage_uri\\ncontent_hash\\ncollected_at\\nsize_bytes\\nsource_format\\nsource_metadata}"];
    RAW_RECORD [label="{RAW_RECORD|id_raw_record\\nrecord_key\\nraw_content\\ndetected_language\\nextracted_at\\nis_usable\\nrejection_reason}"];
    PROCESSING_RUN [label="{PROCESSING_RUN|id_processing\\nstarted_at\\nfinished_at\\npipeline_version\\nstatus\\nnormalized_count\\nrejected_count\\nreport_uri}"];
    NORMALIZED_MESSAGE [label="{NORMALIZED_MESSAGE|id_message\\nnormalized_text\\ntext_sha256\\nlanguage\\ncurrent_label\\nquality_score\\ncontains_pii\\nredaction_status\\ntext_length\\nnormalized_at}"];
    ANNOTATION [label="{ANNOTATION|id_annotation\\nlabel\\nlabel_source\\nconfidence\\ncomment\\nis_validated\\nannotated_at}"];
    DATASET [label="{DATASET|id_dataset\\nname\\nversion_tag\\ntarget_usage\\nstatus\\nfrozen_at\\nitem_count}"];
    DATASET_ITEM [label="{DATASET_ITEM|id_dataset_item\\nsplit_name\\nsample_weight\\nrow_order}"];

    // Associations
    node [shape=ellipse, style=filled, fillcolor="#D1E8E2"];
    PRODUCES [label="PRODUCES"];
    COLLECTS [label="COLLECTS"];
    CONTAINS [label="CONTAINS"];
    TRANSFORMS [label="TRANSFORMS"];
    BECOMES [label="BECOMES"];
    RECEIVES [label="RECEIVES"];
    COMPOSES [label="COMPOSES"];
    BELONGS_TO [label="BELONGS_TO"];

    // Relationships (Edges without arrows)
    SOURCE_SYSTEM -- PRODUCES [label=" 1,1"];
    PRODUCES -- INGESTION_RUN [label=" 0,n"];
    
    INGESTION_RUN -- COLLECTS [label=" 1,1"];
    COLLECTS -- RAW_OBJECT [label=" 0,n"];
    
    RAW_OBJECT -- CONTAINS [label=" 1,1"];
    CONTAINS -- RAW_RECORD [label=" 0,n"];
    
    PROCESSING_RUN -- TRANSFORMS [label=" 1,1"];
    TRANSFORMS -- RAW_RECORD [label=" 0,n"];
    
    RAW_RECORD -- BECOMES [label=" 0,1"];
    BECOMES -- NORMALIZED_MESSAGE [label=" 0,1"];
    
    NORMALIZED_MESSAGE -- RECEIVES [label=" 1,1"];
    RECEIVES -- ANNOTATION [label=" 0,n"];
    
    DATASET -- COMPOSES [label=" 1,1"];
    COMPOSES -- DATASET_ITEM [label=" 1,n"];
    
    DATASET_ITEM -- BELONGS_TO [label=" 1,1"];
    BELONGS_TO -- NORMALIZED_MESSAGE [label=" 0,n"];
}
"""

with open(out_dir / "mcd.dot", "w") as f:
    f.write(mcd_dot)

# ==========================================
# 2. MLD (Logical Model)
# ==========================================
mld_dot = """
digraph MLD {
    rankdir=LR;
    node [shape=none, fontname="Helvetica,Arial,sans-serif", fontsize=10];
    edge [fontname="Helvetica,Arial,sans-serif", fontsize=9, dir=both, arrowtail=crow, arrowhead=tee];

    SourceSystem [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#B4C6E7"><b>data_source_system</b></td></tr>
        <tr><td align="left"><u>id</u> (UUID)</td></tr>
        <tr><td align="left">name (String)</td></tr>
        <tr><td align="left">source_type (String)</td></tr>
        <tr><td align="left">owner_name (String)</td></tr>
        <tr><td align="left">legal_basis (String)</td></tr>
        <tr><td align="left">contains_personal_data (Boolean)</td></tr>
        <tr><td align="left">retention_days (Integer)</td></tr>
        <tr><td align="left">is_active (Boolean)</td></tr>
    </table>>];

    IngestionRun [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#B4C6E7"><b>data_ingestion_run</b></td></tr>
        <tr><td align="left"><u>id</u> (UUID)</td></tr>
        <tr><td align="left"><i>source_system_id</i> (UUID)</td></tr>
        <tr><td align="left">started_at (DateTime)</td></tr>
        <tr><td align="left">finished_at (DateTime)</td></tr>
        <tr><td align="left">status (String)</td></tr>
        <tr><td align="left">trigger_mode (String)</td></tr>
        <tr><td align="left">raw_object_count (Integer)</td></tr>
        <tr><td align="left">raw_record_count (Integer)</td></tr>
        <tr><td align="left">log_message (String)</td></tr>
    </table>>];

    RawObject [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#B4C6E7"><b>data_raw_object</b></td></tr>
        <tr><td align="left"><u>id</u> (UUID)</td></tr>
        <tr><td align="left"><i>ingestion_run_id</i> (UUID)</td></tr>
        <tr><td align="left">external_ref (String)</td></tr>
        <tr><td align="left">object_type (String)</td></tr>
        <tr><td align="left">storage_uri (String)</td></tr>
        <tr><td align="left">source_format (String)</td></tr>
        <tr><td align="left">content_hash (String)</td></tr>
        <tr><td align="left">size_bytes (BigInt)</td></tr>
        <tr><td align="left">source_metadata (JSON)</td></tr>
        <tr><td align="left">collected_at (DateTime)</td></tr>
        <tr><td align="left">retention_until (DateTime)</td></tr>
    </table>>];

    RawRecord [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#B4C6E7"><b>data_raw_record</b></td></tr>
        <tr><td align="left"><u>id</u> (UUID)</td></tr>
        <tr><td align="left"><i>raw_object_id</i> (UUID)</td></tr>
        <tr><td align="left">record_key (String)</td></tr>
        <tr><td align="left">raw_content (String)</td></tr>
        <tr><td align="left">detected_language (String)</td></tr>
        <tr><td align="left">is_usable (Boolean)</td></tr>
        <tr><td align="left">rejection_reason (String)</td></tr>
        <tr><td align="left">extracted_at (DateTime)</td></tr>
    </table>>];

    ProcessingRun [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#B4C6E7"><b>data_processing_run</b></td></tr>
        <tr><td align="left"><u>id</u> (UUID)</td></tr>
        <tr><td align="left">pipeline_version (String)</td></tr>
        <tr><td align="left">started_at (DateTime)</td></tr>
        <tr><td align="left">finished_at (DateTime)</td></tr>
        <tr><td align="left">status (String)</td></tr>
        <tr><td align="left">normalized_count (Integer)</td></tr>
        <tr><td align="left">rejected_count (Integer)</td></tr>
        <tr><td align="left">report_uri (String)</td></tr>
    </table>>];

    NormalizedMessage [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#B4C6E7"><b>data_normalized_message</b></td></tr>
        <tr><td align="left"><u>id</u> (UUID)</td></tr>
        <tr><td align="left"><i>raw_record_id</i> (UUID)</td></tr>
        <tr><td align="left"><i>processing_run_id</i> (UUID)</td></tr>
        <tr><td align="left">normalized_text (String)</td></tr>
        <tr><td align="left">text_sha256 (String)</td></tr>
        <tr><td align="left">language (String)</td></tr>
        <tr><td align="left">current_label (String)</td></tr>
        <tr><td align="left">quality_score (Float)</td></tr>
        <tr><td align="left">contains_pii (Boolean)</td></tr>
        <tr><td align="left">redaction_status (String)</td></tr>
        <tr><td align="left">text_length (Integer)</td></tr>
        <tr><td align="left">normalized_at (DateTime)</td></tr>
    </table>>];

    Annotation [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#B4C6E7"><b>data_annotation</b></td></tr>
        <tr><td align="left"><u>id</u> (UUID)</td></tr>
        <tr><td align="left"><i>normalized_message_id</i> (UUID)</td></tr>
        <tr><td align="left">label (String)</td></tr>
        <tr><td align="left">label_source (String)</td></tr>
        <tr><td align="left">confidence (Float)</td></tr>
        <tr><td align="left">comment (String)</td></tr>
        <tr><td align="left">is_validated (Boolean)</td></tr>
        <tr><td align="left">annotated_at (DateTime)</td></tr>
    </table>>];

    Dataset [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#B4C6E7"><b>data_dataset</b></td></tr>
        <tr><td align="left"><u>id</u> (UUID)</td></tr>
        <tr><td align="left">name (String)</td></tr>
        <tr><td align="left">version_tag (String)</td></tr>
        <tr><td align="left">target_usage (String)</td></tr>
        <tr><td align="left">status (String)</td></tr>
        <tr><td align="left">frozen_at (DateTime)</td></tr>
        <tr><td align="left">item_count (Integer)</td></tr>
    </table>>];

    DatasetItem [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#B4C6E7"><b>data_dataset_item</b></td></tr>
        <tr><td align="left"><u>id</u> (UUID)</td></tr>
        <tr><td align="left"><i>dataset_id</i> (UUID)</td></tr>
        <tr><td align="left"><i>normalized_message_id</i> (UUID)</td></tr>
        <tr><td align="left">split_name (String)</td></tr>
        <tr><td align="left">sample_weight (Float)</td></tr>
        <tr><td align="left">row_order (Integer)</td></tr>
    </table>>];

    // Relationships: arrow indicates Crow (many), tail indicates Tee (one)
    SourceSystem -> IngestionRun [dir=back, arrowtail=tee, arrowhead=crow];
    IngestionRun -> RawObject [dir=back, arrowtail=tee, arrowhead=crow];
    RawObject -> RawRecord [dir=back, arrowtail=tee, arrowhead=crow];
    RawRecord -> NormalizedMessage [dir=back, arrowtail=tee, arrowhead=tee, label="0..1"];
    ProcessingRun -> NormalizedMessage [dir=back, arrowtail=tee, arrowhead=crow];
    NormalizedMessage -> Annotation [dir=back, arrowtail=tee, arrowhead=crow];
    NormalizedMessage -> DatasetItem [dir=back, arrowtail=tee, arrowhead=crow];
    Dataset -> DatasetItem [dir=back, arrowtail=tee, arrowhead=crow];
}
"""

with open(out_dir / "mld.dot", "w") as f:
    f.write(mld_dot)

# ==========================================
# 3. MPD (Physical Model)
# ==========================================
mpd_dot = """
digraph MPD {
    rankdir=LR;
    node [shape=none, fontname="Helvetica,Arial,sans-serif", fontsize=10];
    edge [fontname="Helvetica,Arial,sans-serif", fontsize=9, dir=both, arrowtail=crow, arrowhead=tee];

    SourceSystem [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#A9DFBF"><b>data_source_system</b></td></tr>
        <tr><td align="left"><u>id</u> (uuid) PK [gen_random_uuid()]</td></tr>
        <tr><td align="left">name (text) NOT NULL UNIQUE</td></tr>
        <tr><td align="left">source_type (text) NOT NULL CHECK(...)</td></tr>
        <tr><td align="left">owner_name (text)</td></tr>
        <tr><td align="left">legal_basis (text)</td></tr>
        <tr><td align="left">contains_personal_data (boolean) NOT NULL [false]</td></tr>
        <tr><td align="left">retention_days (integer)</td></tr>
        <tr><td align="left">is_active (boolean) NOT NULL [true]</td></tr>
        <tr><td align="left">created_at (timestamptz) NOT NULL [now()]</td></tr>
        <tr><td align="left">updated_at (timestamptz)</td></tr>
    </table>>];

    IngestionRun [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#A9DFBF"><b>data_ingestion_run</b></td></tr>
        <tr><td align="left"><u>id</u> (uuid) PK</td></tr>
        <tr><td align="left"><i>source_system_id</i> (uuid) NOT NULL FK RESTRICT</td></tr>
        <tr><td align="left">started_at (timestamptz) NOT NULL</td></tr>
        <tr><td align="left">finished_at (timestamptz)</td></tr>
        <tr><td align="left">status (text) NOT NULL CHECK(...)</td></tr>
        <tr><td align="left">trigger_mode (text) NOT NULL</td></tr>
        <tr><td align="left">raw_object_count (integer) NOT NULL [0]</td></tr>
        <tr><td align="left">raw_record_count (integer) NOT NULL [0]</td></tr>
        <tr><td align="left">log_message (text)</td></tr>
        <tr><td align="left">created_at (timestamptz) NOT NULL [now()]</td></tr>
    </table>>];

    RawObject [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#A9DFBF"><b>data_raw_object</b></td></tr>
        <tr><td align="left"><u>id</u> (uuid) PK</td></tr>
        <tr><td align="left"><i>ingestion_run_id</i> (uuid) NOT NULL FK CASCADE</td></tr>
        <tr><td align="left">external_ref (text)</td></tr>
        <tr><td align="left">object_type (text) NOT NULL CHECK(...)</td></tr>
        <tr><td align="left">storage_uri (text)</td></tr>
        <tr><td align="left">source_format (text)</td></tr>
        <tr><td align="left">content_hash (text) NOT NULL</td></tr>
        <tr><td align="left">size_bytes (bigint)</td></tr>
        <tr><td align="left">source_metadata (jsonb) NOT NULL ['{}']</td></tr>
        <tr><td align="left">collected_at (timestamptz) NOT NULL</td></tr>
        <tr><td align="left">retention_until (timestamptz)</td></tr>
        <tr><td align="left">created_at (timestamptz) NOT NULL [now()]</td></tr>
    </table>>];

    RawRecord [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#A9DFBF"><b>data_raw_record</b></td></tr>
        <tr><td align="left"><u>id</u> (uuid) PK</td></tr>
        <tr><td align="left"><i>raw_object_id</i> (uuid) NOT NULL FK CASCADE</td></tr>
        <tr><td align="left">record_key (text) NOT NULL</td></tr>
        <tr><td align="left">raw_content (text) NOT NULL</td></tr>
        <tr><td align="left">detected_language (text)</td></tr>
        <tr><td align="left">is_usable (boolean) NOT NULL [true]</td></tr>
        <tr><td align="left">rejection_reason (text)</td></tr>
        <tr><td align="left">extracted_at (timestamptz) NOT NULL</td></tr>
        <tr><td align="left">created_at (timestamptz) NOT NULL [now()]</td></tr>
    </table>>];

    ProcessingRun [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#A9DFBF"><b>data_processing_run</b></td></tr>
        <tr><td align="left"><u>id</u> (uuid) PK</td></tr>
        <tr><td align="left">pipeline_version (text) NOT NULL</td></tr>
        <tr><td align="left">started_at (timestamptz) NOT NULL</td></tr>
        <tr><td align="left">finished_at (timestamptz)</td></tr>
        <tr><td align="left">status (text) NOT NULL CHECK(...)</td></tr>
        <tr><td align="left">normalized_count (integer) NOT NULL [0]</td></tr>
        <tr><td align="left">rejected_count (integer) NOT NULL [0]</td></tr>
        <tr><td align="left">report_uri (text)</td></tr>
        <tr><td align="left">created_at (timestamptz) NOT NULL [now()]</td></tr>
    </table>>];

    NormalizedMessage [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#A9DFBF"><b>data_normalized_message</b></td></tr>
        <tr><td align="left"><u>id</u> (uuid) PK</td></tr>
        <tr><td align="left"><i>raw_record_id</i> (uuid) NOT NULL FK RESTRICT</td></tr>
        <tr><td align="left"><i>processing_run_id</i> (uuid) NOT NULL FK RESTRICT</td></tr>
        <tr><td align="left">normalized_text (text) NOT NULL</td></tr>
        <tr><td align="left">text_sha256 (text) NOT NULL UNIQUE</td></tr>
        <tr><td align="left">language (text) NOT NULL</td></tr>
        <tr><td align="left">current_label (text) NOT NULL CHECK(...)</td></tr>
        <tr><td align="left">quality_score (real)</td></tr>
        <tr><td align="left">contains_pii (boolean) NOT NULL [false]</td></tr>
        <tr><td align="left">redaction_status (text) NOT NULL [not_required] CHECK(...)</td></tr>
        <tr><td align="left">text_length (integer) NOT NULL</td></tr>
        <tr><td align="left">normalized_at (timestamptz) NOT NULL</td></tr>
        <tr><td align="left">created_at (timestamptz) NOT NULL [now()]</td></tr>
        <tr><td align="left">updated_at (timestamptz)</td></tr>
    </table>>];

    Annotation [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#A9DFBF"><b>data_annotation</b></td></tr>
        <tr><td align="left"><u>id</u> (uuid) PK</td></tr>
        <tr><td align="left"><i>normalized_message_id</i> (uuid) NOT NULL FK CASCADE</td></tr>
        <tr><td align="left">label (text) NOT NULL CHECK(...)</td></tr>
        <tr><td align="left">label_source (text) NOT NULL</td></tr>
        <tr><td align="left">confidence (real) CHECK(...)</td></tr>
        <tr><td align="left">comment (text)</td></tr>
        <tr><td align="left">is_validated (boolean) NOT NULL [false]</td></tr>
        <tr><td align="left">annotated_at (timestamptz) NOT NULL</td></tr>
        <tr><td align="left">created_at (timestamptz) NOT NULL [now()]</td></tr>
    </table>>];

    Dataset [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#A9DFBF"><b>data_dataset</b></td></tr>
        <tr><td align="left"><u>id</u> (uuid) PK</td></tr>
        <tr><td align="left">name (text) NOT NULL</td></tr>
        <tr><td align="left">version_tag (text) NOT NULL UNIQUE</td></tr>
        <tr><td align="left">target_usage (text) NOT NULL</td></tr>
        <tr><td align="left">status (text) NOT NULL CHECK(...)</td></tr>
        <tr><td align="left">frozen_at (timestamptz)</td></tr>
        <tr><td align="left">item_count (integer) NOT NULL [0]</td></tr>
        <tr><td align="left">created_at (timestamptz) NOT NULL [now()]</td></tr>
    </table>>];

    DatasetItem [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">
        <tr><td bgcolor="#A9DFBF"><b>data_dataset_item</b></td></tr>
        <tr><td align="left"><u>id</u> (uuid) PK</td></tr>
        <tr><td align="left"><i>dataset_id</i> (uuid) NOT NULL FK CASCADE</td></tr>
        <tr><td align="left"><i>normalized_message_id</i> (uuid) NOT NULL FK RESTRICT</td></tr>
        <tr><td align="left">split_name (text) NOT NULL CHECK(...)</td></tr>
        <tr><td align="left">sample_weight (real) NOT NULL [1.0]</td></tr>
        <tr><td align="left">row_order (integer)</td></tr>
        <tr><td align="left">created_at (timestamptz) NOT NULL [now()]</td></tr>
    </table>>];

    // Relationships: arrow indicates Crow (many), tail indicates Tee (one)
    SourceSystem -> IngestionRun [dir=back, arrowtail=tee, arrowhead=crow];
    IngestionRun -> RawObject [dir=back, arrowtail=tee, arrowhead=crow];
    RawObject -> RawRecord [dir=back, arrowtail=tee, arrowhead=crow];
    RawRecord -> NormalizedMessage [dir=back, arrowtail=tee, arrowhead=tee, label="0..1"];
    ProcessingRun -> NormalizedMessage [dir=back, arrowtail=tee, arrowhead=crow];
    NormalizedMessage -> Annotation [dir=back, arrowtail=tee, arrowhead=crow];
    NormalizedMessage -> DatasetItem [dir=back, arrowtail=tee, arrowhead=crow];
    Dataset -> DatasetItem [dir=back, arrowtail=tee, arrowhead=crow];
}
"""

with open(out_dir / "mpd.dot", "w") as f:
    f.write(mpd_dot)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate MCD, MLD, MPD diagrams.")
    parser.add_argument("--mcd", action="store_true", help="Generate MCD diagram only")
    parser.add_argument("--mld", action="store_true", help="Generate MLD diagram only")
    parser.add_argument("--mpd", action="store_true", help="Generate MPD diagram only")
    parser.add_argument("--all", action="store_true", help="Generate all diagrams")

    args = parser.parse_args()

    # Default to all if no args provided
    if not (args.mcd or args.mld or args.mpd):
        args.all = True

    if args.all or args.mcd:
        print("Generating MCD...")
        subprocess.run(
            ["dot", "-Tpng", str(out_dir / "mcd.dot"), "-o", str(out_dir / "mcd.png")],
            check=True,
        )
    if args.all or args.mld:
        print("Generating MLD...")
        subprocess.run(
            ["dot", "-Tpng", str(out_dir / "mld.dot"), "-o", str(out_dir / "mld.png")],
            check=True,
        )
    if args.all or args.mpd:
        print("Generating MPD...")
        subprocess.run(
            ["dot", "-Tpng", str(out_dir / "mpd.dot"), "-o", str(out_dir / "mpd.png")],
            check=True,
        )

    print(f"Done! Images in {out_dir}/")

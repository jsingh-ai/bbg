-- BBG dashboard query indexes for the existing OPC collector tables.
-- Review and run this once in MySQL Workbench during a maintenance window.
-- It is safe to rerun: each index is created only when it is missing.

SET @schema_name = DATABASE();

SET @index_exists = (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = @schema_name
      AND table_name = 'opc_tag_values'
      AND index_name = 'idx_opc_tag_values_dashboard'
);
SET @sql = IF(
    @index_exists = 0,
    'CREATE INDEX idx_opc_tag_values_dashboard ON opc_tag_values (tag_id, created_at, value_kind, value_num)',
    'SELECT ''idx_opc_tag_values_dashboard already exists'' AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @index_exists = (
    SELECT COUNT(*)
    FROM information_schema.statistics
    WHERE table_schema = @schema_name
      AND table_name = 'opc_tags'
      AND index_name = 'idx_opc_tags_machine_active_path'
);
SET @sql = IF(
    @index_exists = 0,
    'CREATE INDEX idx_opc_tags_machine_active_path ON opc_tags (machine_id, is_active, opc_path, tag_id)',
    'SELECT ''idx_opc_tags_machine_active_path already exists'' AS message'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

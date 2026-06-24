-- BBG OPC Dashboard tables.
-- Run this in MySQL Workbench after your existing OPC collector schema exists.
-- Do NOT drop or recreate your collector tables.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS opc_machine_sections (
    section_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    machine_id INT UNSIGNED NOT NULL,
    section_key VARCHAR(255) NOT NULL COMMENT 'Parsed section from opc_tags.opc_path, e.g. 020 - unwinder',
    display_label VARCHAR(255) NULL,
    section_photo_path VARCHAR(500) NULL COMMENT 'Relative static path, e.g. opc_photos/020 - Unwinder.jpeg',
    is_visible TINYINT(1) NOT NULL DEFAULT 1,
    sort_order INT NOT NULL DEFAULT 0,
    box_x_pct DECIMAL(7,4) NULL,
    box_y_pct DECIMAL(7,4) NULL,
    box_w_pct DECIMAL(7,4) NULL,
    box_h_pct DECIMAL(7,4) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (section_id),
    UNIQUE KEY uq_machine_section_key (machine_id, section_key),
    KEY idx_machine_visible_sort (machine_id, is_visible, sort_order),

    CONSTRAINT fk_opc_machine_sections_machine
        FOREIGN KEY (machine_id)
        REFERENCES opc_machines(machine_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS opc_tag_display_config (
    config_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    machine_id INT UNSIGNED NOT NULL,
    tag_id INT UNSIGNED NOT NULL,
    section_key VARCHAR(255) NOT NULL,
    is_visible TINYINT(1) NOT NULL DEFAULT 1,
    show_in_history_default TINYINT(1) NOT NULL DEFAULT 1,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (config_id),
    UNIQUE KEY uq_machine_tag_config (machine_id, tag_id),
    KEY idx_machine_section_visible (machine_id, section_key, is_visible),
    KEY idx_tag_display_tag (tag_id),

    CONSTRAINT fk_opc_tag_display_config_machine
        FOREIGN KEY (machine_id)
        REFERENCES opc_machines(machine_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_opc_tag_display_config_tag
        FOREIGN KEY (tag_id)
        REFERENCES opc_tags(tag_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS opc_recipes (
    recipe_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    machine_id INT UNSIGNED NOT NULL,
    recipe_name VARCHAR(150) NOT NULL,
    recipe_code VARCHAR(100) NULL,
    description TEXT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (recipe_id),
    UNIQUE KEY uq_machine_recipe_name (machine_id, recipe_name),
    KEY idx_machine_recipe_active (machine_id, is_active, recipe_name),

    CONSTRAINT fk_opc_recipes_machine
        FOREIGN KEY (machine_id)
        REFERENCES opc_machines(machine_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS opc_recipe_limits (
    limit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    recipe_id BIGINT UNSIGNED NOT NULL,
    machine_id INT UNSIGNED NOT NULL,
    tag_id INT UNSIGNED NOT NULL,
    section_key VARCHAR(255) NOT NULL,
    min_value DOUBLE NULL,
    max_value DOUBLE NULL,
    is_enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (limit_id),
    UNIQUE KEY uq_recipe_tag_limit (recipe_id, tag_id),
    KEY idx_machine_recipe_section (machine_id, recipe_id, section_key),
    KEY idx_recipe_enabled (recipe_id, is_enabled),
    KEY idx_limit_tag (tag_id),

    CONSTRAINT fk_opc_recipe_limits_recipe
        FOREIGN KEY (recipe_id)
        REFERENCES opc_recipes(recipe_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_opc_recipe_limits_machine
        FOREIGN KEY (machine_id)
        REFERENCES opc_machines(machine_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_opc_recipe_limits_tag
        FOREIGN KEY (tag_id)
        REFERENCES opc_tags(tag_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS opc_machine_active_recipe (
    machine_id INT UNSIGNED NOT NULL,
    recipe_id BIGINT UNSIGNED NULL,
    selection_mode ENUM('manual', 'automatic') NOT NULL DEFAULT 'manual',
    selected_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (machine_id),
    KEY idx_active_recipe_recipe (recipe_id),

    CONSTRAINT fk_opc_machine_active_recipe_machine
        FOREIGN KEY (machine_id)
        REFERENCES opc_machines(machine_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_opc_machine_active_recipe_recipe
        FOREIGN KEY (recipe_id)
        REFERENCES opc_recipes(recipe_id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS opc_alert_events (
    alert_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    machine_id INT UNSIGNED NOT NULL,
    recipe_id BIGINT UNSIGNED NULL,
    tag_id INT UNSIGNED NOT NULL,
    section_key VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) NULL,
    alert_type ENUM('LOW', 'HIGH', 'LIMIT') NOT NULL DEFAULT 'LIMIT',
    min_value DOUBLE NULL,
    max_value DOUBLE NULL,
    trigger_value DOUBLE NOT NULL,
    current_value DOUBLE NULL,
    triggered_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    last_seen_at DATETIME(3) NULL,
    returned_to_range_at DATETIME(3) NULL,
    is_currently_out_of_range TINYINT(1) NOT NULL DEFAULT 1,
    is_acknowledged TINYINT(1) NOT NULL DEFAULT 0,
    acknowledged_at DATETIME(3) NULL,
    acknowledged_by VARCHAR(100) NULL,
    acknowledge_note VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (alert_id),
    KEY idx_alert_active (machine_id, is_acknowledged, is_currently_out_of_range, triggered_at),
    KEY idx_alert_section (machine_id, section_key, is_acknowledged),
    KEY idx_alert_recipe_tag (machine_id, recipe_id, tag_id, is_acknowledged),
    KEY idx_alert_triggered (triggered_at),

    CONSTRAINT fk_opc_alert_events_machine
        FOREIGN KEY (machine_id)
        REFERENCES opc_machines(machine_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_opc_alert_events_recipe
        FOREIGN KEY (recipe_id)
        REFERENCES opc_recipes(recipe_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_opc_alert_events_tag
        FOREIGN KEY (tag_id)
        REFERENCES opc_tags(tag_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

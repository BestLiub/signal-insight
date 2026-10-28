SET NAMES utf8mb4;
CREATE DATABASE IF NOT EXISTS `signal_warehouse` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
USE `signal_warehouse`;

-- dim_area
DROP TABLE IF EXISTS `dim_area`;
CREATE TABLE `dim_area` (
  `area` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `kind` text COLLATE utf8mb4_bin,
  `center_lng` double DEFAULT NULL,
  `center_lat` double DEFAULT NULL,
  `radius_m` double DEFAULT NULL,
  `source` text COLLATE utf8mb4_bin,
  `note` text COLLATE utf8mb4_bin
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- dim_metric
DROP TABLE IF EXISTS `dim_metric`;
CREATE TABLE `dim_metric` (
  `metric` text COLLATE utf8mb4_bin,
  `meaning` text COLLATE utf8mb4_bin,
  `definition` text COLLATE utf8mb4_bin,
  `params` text COLLATE utf8mb4_bin,
  `source_table` text COLLATE utf8mb4_bin,
  `version` text COLLATE utf8mb4_bin
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- dim_hotspot
DROP TABLE IF EXISTS `dim_hotspot`;
CREATE TABLE `dim_hotspot` (
  `name` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `lng` double DEFAULT NULL,
  `lat` double DEFAULT NULL,
  `radius_m` bigint DEFAULT NULL,
  `note` text COLLATE utf8mb4_bin
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ads_area_daily
DROP TABLE IF EXISTS `ads_area_daily`;
CREATE TABLE `ads_area_daily` (
  `dt` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `area` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `visitors_all` double DEFAULT NULL,
  `evening_visitors` double DEFAULT NULL,
  `stay_min_p50` double DEFAULT NULL,
  `censored_share` double DEFAULT NULL,
  `arrive_hour_p50` double DEFAULT NULL,
  `night_known_share` double DEFAULT NULL,
  `night_dist_km_p50` double DEFAULT NULL,
  `night_dist_km_p90` double DEFAULT NULL,
  `inbound_share` double DEFAULT NULL,
  `suppressed` bigint DEFAULT NULL,
  `is_synthetic` bigint DEFAULT NULL,
  KEY `idx_ads_area_daily_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ads_area_hourly
DROP TABLE IF EXISTS `ads_area_hourly`;
CREATE TABLE `ads_area_hourly` (
  `dt` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `area` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `hour` bigint DEFAULT NULL,
  `users` double DEFAULT NULL,
  `locatable` bigint DEFAULT NULL,
  `share` double DEFAULT NULL,
  `suppressed` bigint DEFAULT NULL,
  `is_synthetic` bigint DEFAULT NULL,
  KEY `idx_ads_area_hourly_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ads_area_segment
DROP TABLE IF EXISTS `ads_area_segment`;
CREATE TABLE `ads_area_segment` (
  `dt` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `area` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `segment` text COLLATE utf8mb4_bin,
  `users` double DEFAULT NULL,
  `share` double DEFAULT NULL,
  `suppressed` bigint DEFAULT NULL,
  `is_synthetic` bigint DEFAULT NULL,
  KEY `idx_ads_area_segment_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ads_area_radius
DROP TABLE IF EXISTS `ads_area_radius`;
CREATE TABLE `ads_area_radius` (
  `dt` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `area` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `band` text COLLATE utf8mb4_bin,
  `users` double DEFAULT NULL,
  `band_order` bigint DEFAULT NULL,
  `share` double DEFAULT NULL,
  `cum_share` double DEFAULT NULL,
  `suppressed` bigint DEFAULT NULL,
  `is_synthetic` bigint DEFAULT NULL,
  KEY `idx_ads_area_radius_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ads_area_origin
DROP TABLE IF EXISTS `ads_area_origin`;
CREATE TABLE `ads_area_origin` (
  `dt` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `area` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `origin` text COLLATE utf8mb4_bin,
  `users` double DEFAULT NULL,
  `share` double DEFAULT NULL,
  `suppressed` bigint DEFAULT NULL,
  `is_synthetic` bigint DEFAULT NULL,
  KEY `idx_ads_area_origin_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ads_area_linkage
DROP TABLE IF EXISTS `ads_area_linkage`;
CREATE TABLE `ads_area_linkage` (
  `dt` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `area` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `other_area` text COLLATE utf8mb4_bin,
  `evening_visitors` bigint DEFAULT NULL,
  `users_any` double DEFAULT NULL,
  `users_before` double DEFAULT NULL,
  `users_after` double DEFAULT NULL,
  `share_any` double DEFAULT NULL,
  `share_before` double DEFAULT NULL,
  `share_after` double DEFAULT NULL,
  `is_synthetic` bigint DEFAULT NULL,
  KEY `idx_ads_area_linkage_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ads_hex_hourly
DROP TABLE IF EXISTS `ads_hex_hourly`;
CREATE TABLE `ads_hex_hourly` (
  `dt` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `hour` bigint DEFAULT NULL,
  `q` bigint DEFAULT NULL,
  `r` bigint DEFAULT NULL,
  `users` bigint DEFAULT NULL,
  `center_lng` double DEFAULT NULL,
  `center_lat` double DEFAULT NULL,
  `size_m` bigint DEFAULT NULL,
  `is_synthetic` bigint DEFAULT NULL,
  KEY `idx_ads_hex_hourly_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ads_od_district
DROP TABLE IF EXISTS `ads_od_district`;
CREATE TABLE `ads_od_district` (
  `dt` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `o_district` text COLLATE utf8mb4_bin,
  `d_district` text COLLATE utf8mb4_bin,
  `trips` double DEFAULT NULL,
  `users` double DEFAULT NULL,
  `suppressed` bigint DEFAULT NULL,
  `is_synthetic` bigint DEFAULT NULL,
  KEY `idx_ads_od_district_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ads_dq_partition
DROP TABLE IF EXISTS `ads_dq_partition`;
CREATE TABLE `ads_dq_partition` (
  `dt` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `rows` bigint DEFAULT NULL,
  `users` bigint DEFAULT NULL,
  `rows_per_user` double DEFAULT NULL,
  `volume_ratio` double DEFAULT NULL,
  `valid_hours` double DEFAULT NULL,
  `dup_rate` double DEFAULT NULL,
  `cell_match_rate` double DEFAULT NULL,
  `n_fail` bigint DEFAULT NULL,
  `n_warn` bigint DEFAULT NULL,
  `gate_status` text COLLATE utf8mb4_bin,
  `pipeline_status` text COLLATE utf8mb4_bin,
  `baseline_source` text COLLATE utf8mb4_bin,
  `is_synthetic` bigint DEFAULT NULL,
  `hourly_json` text COLLATE utf8mb4_bin,
  KEY `idx_ads_dq_partition_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ads_dq_rule
DROP TABLE IF EXISTS `ads_dq_rule`;
CREATE TABLE `ads_dq_rule` (
  `dt` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `rule_id` text COLLATE utf8mb4_bin,
  `rule_name` text COLLATE utf8mb4_bin,
  `value` double DEFAULT NULL,
  `threshold` text COLLATE utf8mb4_bin,
  `result` text COLLATE utf8mb4_bin,
  `is_synthetic` bigint DEFAULT NULL,
  KEY `idx_ads_dq_rule_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

-- ads_dq_clean_steps
DROP TABLE IF EXISTS `ads_dq_clean_steps`;
CREATE TABLE `ads_dq_clean_steps` (
  `dt` varchar(191) COLLATE utf8mb4_bin DEFAULT NULL,
  `step_no` bigint DEFAULT NULL,
  `step` text COLLATE utf8mb4_bin,
  `rows_before` bigint DEFAULT NULL,
  `rows_removed` bigint DEFAULT NULL,
  `rows_after` bigint DEFAULT NULL,
  `is_synthetic` bigint DEFAULT NULL,
  KEY `idx_ads_dq_clean_steps_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

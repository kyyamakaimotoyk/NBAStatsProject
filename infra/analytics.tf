# =============================================================================
# Analytics foundation: Athena over the CloudFront logs, for QuickSight (4.4+)
# =============================================================================
# QuickSight reads through Athena, and Athena reads files in S3 via a TABLE that
# describes their format. We define that table (and its database + an Athena
# workgroup with a results location) in Terraform so it's reproducible — then
# point QuickSight at it from the console.
#
# The data: CloudFront access logs delivered to the logs bucket under cf-site/
# (Week 4.4). Standard CloudFront log format = 33 tab-separated columns with two
# leading "#"-comment lines we skip.
# =============================================================================


# Glue Data Catalog = the metastore Athena uses. A "database" is just a namespace.
resource "aws_glue_catalog_database" "logs" {
  name = "hoopmodel_logs"
}


# The table describing the CloudFront log files. Athena/QuickSight query this.
resource "aws_glue_catalog_table" "cf_site_logs" {
  name          = "cf_site_logs"
  database_name = aws_glue_catalog_database.logs.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL                 = "TRUE"
    "skip.header.line.count" = "2" # CloudFront's #Version and #Fields lines
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.logs.bucket}/cf-site/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe"
      parameters = {
        "field.delim"          = "\t"
        "serialization.format" = "\t"
      }
    }

    # The 33 standard CloudFront log columns, in order.
    columns {
      name = "date"
      type = "date"
    }
    columns {
      name = "time"
      type = "string"
    }
    columns {
      name = "location"
      type = "string"
    }
    columns {
      name = "bytes"
      type = "bigint"
    }
    columns {
      name = "request_ip"
      type = "string"
    }
    columns {
      name = "method"
      type = "string"
    }
    columns {
      name = "host"
      type = "string"
    }
    columns {
      name = "uri"
      type = "string"
    }
    columns {
      name = "status"
      type = "int"
    }
    columns {
      name = "referrer"
      type = "string"
    }
    columns {
      name = "user_agent"
      type = "string"
    }
    columns {
      name = "query_string"
      type = "string"
    }
    columns {
      name = "cookie"
      type = "string"
    }
    columns {
      name = "result_type"
      type = "string"
    }
    columns {
      name = "request_id"
      type = "string"
    }
    columns {
      name = "host_header"
      type = "string"
    }
    columns {
      name = "request_protocol"
      type = "string"
    }
    columns {
      name = "request_bytes"
      type = "bigint"
    }
    columns {
      name = "time_taken"
      type = "float"
    }
    columns {
      name = "xforwarded_for"
      type = "string"
    }
    columns {
      name = "ssl_protocol"
      type = "string"
    }
    columns {
      name = "ssl_cipher"
      type = "string"
    }
    columns {
      name = "response_result_type"
      type = "string"
    }
    columns {
      name = "http_version"
      type = "string"
    }
    columns {
      name = "fle_status"
      type = "string"
    }
    columns {
      name = "fle_encrypted_fields"
      type = "int"
    }
    columns {
      name = "c_port"
      type = "int"
    }
    columns {
      name = "time_to_first_byte"
      type = "float"
    }
    columns {
      name = "x_edge_detailed_result_type"
      type = "string"
    }
    columns {
      name = "sc_content_type"
      type = "string"
    }
    columns {
      name = "sc_content_len"
      type = "bigint"
    }
    columns {
      name = "sc_range_start"
      type = "bigint"
    }
    columns {
      name = "sc_range_end"
      type = "bigint"
    }
  }
}


# Athena workgroup with a results location. QuickSight (and you) run queries here;
# without a results location, Athena queries fail. Results land in their own
# prefix, separate from the raw logs.
resource "aws_athena_workgroup" "main" {
  name = var.project

  configuration {
    result_configuration {
      output_location = "s3://${aws_s3_bucket.logs.bucket}/athena-results/"
    }
  }
}


# -----------------------------------------------------------------------------
# Advisor input corpus — JSON records written by api/advisor.py, one per
# request, under advisor_inputs/year=/month=/day=/. Partition projection means
# no crawler and no MSCK REPAIR: Athena derives partitions from the key layout.
# -----------------------------------------------------------------------------
resource "aws_glue_catalog_table" "advisor_inputs" {
  name          = "advisor_inputs"
  database_name = aws_glue_catalog_database.logs.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL                    = "TRUE"
    "projection.enabled"        = "true"
    "projection.year.type"      = "integer"
    "projection.year.range"     = "2026,2035"
    "projection.month.type"     = "integer"
    "projection.month.range"    = "1,12"
    "projection.month.digits"   = "2"
    "projection.day.type"       = "integer"
    "projection.day.range"      = "1,31"
    "projection.day.digits"     = "2"
    "storage.location.template" = "s3://${aws_s3_bucket.logs.bucket}/advisor_inputs/year=$${year}/month=$${month}/day=$${day}/"
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.logs.bucket}/advisor_inputs/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }

    columns {
      name = "ts"
      type = "string"
    }
    columns {
      name = "outcome"
      type = "string"
    }
    columns {
      name = "ip_hash"
      type = "string"
    }
    columns {
      name = "scoring_type"
      type = "string"
    }
    columns {
      name = "slate_date"
      type = "string"
    }
    columns {
      name = "prompt"
      type = "string"
    }
    columns {
      name = "roster"
      type = "string"
    }
    columns {
      name = "matchup_score"
      type = "string"
    }
    columns {
      name = "tokens_in"
      type = "bigint"
    }
    columns {
      name = "tokens_out"
      type = "bigint"
    }
  }
}

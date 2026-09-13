# Descriptive decomposition of recorded Facebook SMS-verification prices.
# Run from the repository root after Python data preparation.
# The script reads validated prepared data; it does not alter the raw archive.

suppressPackageStartupMessages(library(tidyverse))

check <- function(condition, message) {
  if (!isTRUE(condition)) stop(message, call. = FALSE)
}

if (!file.exists("R/analyze_prices.R")) {
  stop("Set the working directory to the repository root.", call. = FALSE)
}
project_dir <- "."

input_file <- file.path(project_dir, "data", "processed", "facebook_vendor_day_analytical.csv")
audit_file <- file.path(project_dir, "output", "tables", "data_preparation_audit.csv")
table_dir <- file.path(project_dir, "output", "tables")
figure_dir <- file.path(project_dir, "output", "figures")
check(file.exists(input_file), paste("Missing prepared input:", input_file))
check(file.exists(audit_file), paste("Missing preparation audit:", audit_file))
check(requireNamespace("digest", quietly = TRUE),
      "The digest package is needed to verify the prepared-input fingerprint.")

# 1. Import and verify the prepared input and its key/sample structure.
# Input: one calendar-complete vendor-day CSV and its preparation audit.
# Output: typed vendor rows and one country-day row per calendar date.
expected_sha256 <- "0eca581c1e37ed2df40e7750bb40a13e275c5dd8dea5028f229d1563f886b8c2"
actual_sha256 <- digest::digest(input_file, algo = "sha256", file = TRUE)
check(identical(actual_sha256, expected_sha256),
      "The analytical CSV differs from the validated prepared file. Investigate before analysing.")

stage2_audit <- read_csv(audit_file, col_types = cols(.default = col_character()),
                         show_col_types = FALSE)
check(nrow(problems(stage2_audit)) == 0, "Preparation audit has CSV parsing problems.")
check(all(c("check", "actual", "status") %in% names(stage2_audit)),
      "Preparation audit lacks required columns.")
check(sum(stage2_audit$status == "PASS") == 53 &&
        sum(stage2_audit$status == "INFO") == 6 &&
        !any(stage2_audit$status == "FAIL"),
      "Preparation audit no longer has the validated 53 PASS / 6 INFO / 0 FAIL record.")
check(stage2_audit$actual[stage2_audit$check == "analytical_csv_sha256"] == expected_sha256,
      "Preparation audit fingerprint does not match the validated analytical CSV.")

vendor_days <- read_csv(
  input_file,
  na = "",
  show_col_types = FALSE,
  col_types = cols(
    .default = col_guess(),
    date = col_date(format = "%Y-%m-%d"),
    previous_date = col_date(format = "%Y-%m-%d"),
    country_id = col_character(),
    country_name = col_character(),
    service_id = col_character(),
    service_name = col_character(),
    vendor = col_character(),
    positive_vendor_set = col_character(),
    previous_positive_vendor_set = col_character(),
    pair_status = col_character(),
    row_observed = col_logical(),
    country_day_valid = col_logical(),
    positive_stock = col_logical(),
    previous_positive_stock = col_logical(),
    valid_adjacent_pair = col_logical(),
    vendor_set_unchanged = col_logical(),
    primary_pair_eligible = col_logical(),
    vendor_set_change_pair = col_logical(),
    count_reconstruction_ok = col_logical(),
    price_reconstruction_ok = col_logical(),
    share_sum_ok = col_logical()
  )
)
check(nrow(problems(vendor_days)) == 0, "Analytical CSV has parsing problems.")

required <- c(
  "date", "previous_date", "country_id", "country_name", "service_id",
  "service_name", "vendor", "row_observed", "country_day_valid",
  "stock_count", "positive_stock", "price_usd", "stock_share",
  "previous_price_usd", "previous_stock_share", "previous_positive_stock",
  "positive_vendor_count", "positive_vendor_set", "previous_positive_vendor_set",
  "source_combined_price_usd", "previous_source_combined_price_usd",
  "net_combined_price_change_usd", "valid_adjacent_pair",
  "vendor_set_unchanged", "primary_pair_eligible", "vendor_set_change_pair",
  "pair_status", "count_reconstruction_ok", "price_reconstruction_ok", "share_sum_ok"
)
check(all(required %in% names(vendor_days)),
      paste("Analytical CSV is missing:", paste(setdiff(required, names(vendor_days)), collapse = ", ")))
check(inherits(vendor_days$date, "Date") && inherits(vendor_days$previous_date, "Date"),
      "Date columns were not parsed as dates.")
numeric_fields <- c("stock_count", "price_usd", "stock_share", "previous_price_usd",
                    "previous_stock_share", "positive_vendor_count",
                    "source_combined_price_usd", "previous_source_combined_price_usd",
                    "net_combined_price_change_usd")
check(all(vapply(vendor_days[numeric_fields], is.numeric, logical(1))),
      "A required stock, share or price field was not parsed as numeric.")
flag_fields <- c("row_observed", "country_day_valid", "positive_stock",
                 "previous_positive_stock", "valid_adjacent_pair", "vendor_set_unchanged",
                 "primary_pair_eligible", "vendor_set_change_pair",
                 "count_reconstruction_ok", "price_reconstruction_ok", "share_sum_ok")
check(all(vapply(vendor_days[flag_fields], is.logical, logical(1))),
      "A required preparation flag was not parsed as logical.")
check(all(vapply(vendor_days[flag_fields], function(x) !anyNA(x), logical(1))),
      "A required preparation flag contains a missing value.")

check(nrow(vendor_days) == 4332, "Expected 4,332 calendar-complete vendor-day rows.")
check(nrow(distinct(vendor_days, country_id, service_id, vendor, date)) == 4332,
      "Duplicate country-service-vendor-date keys found.")
check(setequal(unique(vendor_days$country_id), c("GB", "US", "ID")),
      "Country scope differs from the fixed research scope.")
check(all(vendor_days$service_id == "fb" & vendor_days$service_name == "Facebook"),
      "The analytical input contains an unexpected service identifier or name.")
check(setequal(unique(vendor_days$vendor),
               c("SMSPVA", "SMSHub", "SMS-Activate", "5SIM")),
      "Vendor scope differs from the fixed research scope.")
check(all(vendor_days$country_name[vendor_days$country_id == "GB"] == "United Kingdom") &&
        all(vendor_days$country_name[vendor_days$country_id == "US"] == "United States") &&
        all(vendor_days$country_name[vendor_days$country_id == "ID"] == "Indonesia"),
      "Country identifier/name mapping is inconsistent.")

day_fields <- c("row_observed", "country_day_valid", "source_combined_price_usd",
                "previous_source_combined_price_usd", "net_combined_price_change_usd",
                "positive_vendor_count", "positive_vendor_set",
                "previous_positive_vendor_set", "previous_date", "valid_adjacent_pair",
                "vendor_set_unchanged", "primary_pair_eligible",
                "vendor_set_change_pair", "pair_status")
day_consistency <- vendor_days %>%
  group_by(country_id, date) %>%
  summarise(vendor_rows = n(), distinct_vendors = n_distinct(vendor),
            across(all_of(day_fields), n_distinct), .groups = "drop")
check(nrow(day_consistency) == 1083 &&
        all(day_consistency$vendor_rows == 4) &&
        all(day_consistency$distinct_vendors == 4),
      "Each of the 1,083 country-calendar dates must have exactly four vendors.")
check(all(as.matrix(day_consistency[day_fields]) == 1),
      "The four vendor rows disagree on a country-day field or pair flag.")

country_days <- vendor_days %>% distinct(country_id, date, .keep_all = TRUE)
approved_dates <- seq.Date(as.Date("2024-08-01"), as.Date("2025-07-27"), by = "day")
for (market in c("GB", "US", "ID")) {
  market_dates <- sort(country_days$date[country_days$country_id == market])
  check(length(market_dates) == length(approved_dates) &&
          all(market_dates == approved_dates),
        paste("Calendar coverage differs for", market))
}
check(all(country_days$country_day_valid == country_days$row_observed),
      "Unexpected invalid observed day or valid missing day.")
check(all(is.finite(vendor_days$stock_count[vendor_days$row_observed])) &&
        all(vendor_days$stock_count[vendor_days$row_observed] >= 0),
      "Observed stock must be finite and nonnegative.")
check(all(is.finite(vendor_days$price_usd[vendor_days$positive_stock])) &&
        all(vendor_days$price_usd[vendor_days$positive_stock] > 0),
      "Positive-stock vendor has an invalid recorded-USD price.")
check(all(vendor_days$count_reconstruction_ok[vendor_days$row_observed]) &&
        all(vendor_days$price_reconstruction_ok[vendor_days$row_observed]) &&
        all(vendor_days$share_sum_ok[vendor_days$row_observed]),
      "A stock, weighted-price or share reconstruction flag failed.")

# Each pair flag is repeated on four vendor rows; count country-days, not vendor rows.
sample_counts <- country_days %>%
  group_by(country_id) %>%
  summarise(observed_days = sum(row_observed),
            valid_pairs = sum(valid_adjacent_pair),
            stable_pairs = sum(primary_pair_eligible),
            changed_pairs = sum(vendor_set_change_pair),
            .groups = "drop") %>%
  arrange(match(country_id, c("GB", "US", "ID")))
expected_counts <- tibble(
  country_id = c("GB", "US", "ID"),
  observed_days = c(360L, 360L, 360L),
  valid_pairs = c(358L, 358L, 358L),
  stable_pairs = c(325L, 326L, 350L),
  changed_pairs = c(33L, 32L, 8L)
)
for (field in names(expected_counts)) {
  check(identical(sample_counts[[field]], expected_counts[[field]]),
        paste("Validated preparation count differs for:", field))
}
check(all(country_days$valid_adjacent_pair ==
            (country_days$primary_pair_eligible | country_days$vendor_set_change_pair)),
      "A valid pair is outside the two specified vendor-set groups.")
check(all(as.integer(country_days$date[country_days$valid_adjacent_pair] -
                       country_days$previous_date[country_days$valid_adjacent_pair]) == 1),
      "A valid pair does not compare consecutive calendar days.")
check(all(!country_days$valid_adjacent_pair[country_days$date %in%
                                              as.Date(c("2024-12-30", "2024-12-31"))]),
      "The 30 December gap was treated as an adjacent-day comparison.")
check(all(country_days$pair_status[country_days$date == as.Date("2024-12-30")] ==
            "current_day_missing") &&
        all(country_days$pair_status[country_days$date == as.Date("2024-12-31")] ==
              "previous_day_missing"),
      "The missing-date exclusions are not labelled correctly.")

cat("\nANALYTICAL INPUT VALIDATION PASSED\n")
cat("Analytical CSV SHA-256:", actual_sha256, "\n")
print(as.data.frame(sample_counts), row.names = FALSE)
cat("Missing date: 2024-12-30 in GB, US and ID; 2024-12-31 has no valid prior-day pair.\n")

# 2. Exact symmetric decomposition on eligible unchanged-set pairs only.
# Input: current and checked previous vendor prices and advertised-stock shares.
# Output: one price component, weight component and observed net change per pair.
eligible_vendors <- vendor_days %>%
  filter(primary_pair_eligible, positive_stock)
check(all(eligible_vendors$previous_positive_stock),
      "An eligible pair has a vendor positive today but not yesterday.")
check(all(eligible_vendors$positive_vendor_set ==
            eligible_vendors$previous_positive_vendor_set) &&
        all(eligible_vendors$positive_vendor_count >= 2),
      "An eligible pair does not have an unchanged set of at least two positive-stock vendors.")
check(all(vapply(eligible_vendors[c("price_usd", "previous_price_usd",
                                    "stock_share", "previous_stock_share")],
                 function(x) all(is.finite(x)), logical(1))),
      "An eligible vendor lacks a finite current or previous price/share.")

share_checks <- eligible_vendors %>%
  group_by(country_id, date) %>%
  summarise(vendors = n(), expected_vendors = first(positive_vendor_count),
            today_share = sum(stock_share), yesterday_share = sum(previous_stock_share),
            .groups = "drop")
check(all(share_checks$vendors == share_checks$expected_vendors) &&
        all(abs(share_checks$today_share - 1) <= 1e-12) &&
        all(abs(share_checks$yesterday_share - 1) <= 1e-12),
      "Eligible vendor count or current/previous stock shares do not reconcile.")

pair_components <- eligible_vendors %>%
  mutate(
    price_term_usd = ((stock_share + previous_stock_share) / 2) *
      (price_usd - previous_price_usd),
    weight_term_usd = ((price_usd + previous_price_usd) / 2) *
      (stock_share - previous_stock_share)
  ) %>%
  group_by(country_id, country_name, date) %>%
  summarise(
    previous_date = first(previous_date),
    positive_vendor_count = n(),
    price_component_usd = sum(price_term_usd),
    weight_component_usd = sum(weight_term_usd),
    observed_net_change_usd = first(net_combined_price_change_usd),
    today_weighted_price_usd = first(source_combined_price_usd),
    previous_weighted_price_usd = first(previous_source_combined_price_usd),
    .groups = "drop"
  ) %>%
  arrange(country_id, date) %>%
  mutate(
    component_sum_usd = price_component_usd + weight_component_usd,
    identity_difference_usd = component_sum_usd - observed_net_change_usd,
    identity_tolerance_usd = 2e-10 +
      1e-8 * (abs(today_weighted_price_usd) + abs(previous_weighted_price_usd))
  )
check(nrow(pair_components) == 1001 &&
        nrow(distinct(pair_components, country_id, date)) == 1001,
      "The decomposition must contain 1,001 unique eligible country-day pairs.")
check(all(is.finite(pair_components$identity_difference_usd)) &&
        all(abs(pair_components$identity_difference_usd) <=
              pair_components$identity_tolerance_usd),
      "Price plus weight component does not equal observed change for every eligible pair.")
check(all(abs(pair_components$observed_net_change_usd -
                (pair_components$today_weighted_price_usd -
                   pair_components$previous_weighted_price_usd)) <=
              pair_components$identity_tolerance_usd),
      "Prepared observed net change does not equal today minus yesterday's source price.")
cat("\nDECOMPOSITION VALIDATION PASSED\n")
cat("Eligible pairs:", nrow(pair_components), "\n")
cat("Identity failures: 0; maximum absolute identity difference:",
    format(max(abs(pair_components$identity_difference_usd)), scientific = TRUE), "USD\n")

# 3. Country-specific descriptive summaries and vendor-set selection check.
# Input: eligible pair components; all valid pair-level source price changes.
# Output: primary country table and stable/change-set comparison table.
primary_summary <- pair_components %>%
  mutate(abs_price = abs(price_component_usd),
         abs_weight = abs(weight_component_usd),
         components_offset = price_component_usd * weight_component_usd < 0) %>%
  group_by(country_id, country_name) %>%
  summarise(
    eligible_pairs = n(),
    mean_abs_price_component_usd = mean(abs_price),
    median_abs_price_component_usd = median(abs_price),
    mean_abs_weight_component_usd = mean(abs_weight),
    median_abs_weight_component_usd = median(abs_weight),
    max_abs_price_component_usd = max(abs_price),
    max_abs_weight_component_usd = max(abs_weight),
    offsetting_sign_pairs = sum(components_offset),
    .groups = "drop"
  ) %>%
  arrange(match(country_id, c("GB", "US", "ID")))
check(identical(primary_summary$eligible_pairs, c(325L, 326L, 350L)),
      "Primary summary pair counts differ from the validated preparation counts.")

valid_pairs <- country_days %>%
  filter(valid_adjacent_pair) %>%
  mutate(vendor_set_group = if_else(vendor_set_change_pair,
                                    "Changing set", "Stable set"),
         abs_weighted_price_change_usd = abs(net_combined_price_change_usd))
check(nrow(valid_pairs) == 1074 &&
        all(is.finite(valid_pairs$abs_weighted_price_change_usd)),
      "Selection check lacks 1,074 valid pairs with finite combined-price changes.")
selection_groups <- valid_pairs %>%
  group_by(country_id, country_name, vendor_set_group) %>%
  summarise(
    group_pairs = n(),
    mean_abs_combined_change_usd = mean(abs_weighted_price_change_usd),
    median_abs_combined_change_usd = median(abs_weighted_price_change_usd),
    max_abs_combined_change_usd = max(abs_weighted_price_change_usd),
    .groups = "drop"
  )
selection_shares <- valid_pairs %>%
  group_by(country_id) %>%
  summarise(
    changing_set_share_of_valid_pairs = mean(vendor_set_group == "Changing set"),
    changing_set_share_of_absolute_movement =
      if (sum(abs_weighted_price_change_usd) == 0) NA_real_ else
        sum(abs_weighted_price_change_usd[vendor_set_group == "Changing set"]) /
        sum(abs_weighted_price_change_usd),
    .groups = "drop"
  )
selection_check <- selection_groups %>%
  left_join(selection_shares, by = "country_id") %>%
  arrange(match(country_id, c("GB", "US", "ID")), vendor_set_group)
check(nrow(selection_check) == 6, "Selection check requires stable/change rows for each country.")
check(all(selection_check$group_pairs[selection_check$vendor_set_group == "Changing set"] ==
            c(33L, 32L, 8L)),
      "Changing-set selection counts differ from the validated preparation counts.")
cat("\nPRIMARY COUNTRY SUMMARY (recorded USD per verification)\n")
print(as.data.frame(primary_summary), row.names = FALSE)
cat("\nVENDOR-SET SELECTION CHECK (shares repeat across the two rows for each country)\n")
print(as.data.frame(selection_check), row.names = FALSE)
cat("Changing-set pairs are described but never decomposed.\n")

# 4. Two figures. Plot segments prevent a line from crossing an
# unavailable day; the decomposition uses points so no excluded pair is joined.
# Input: calendar-complete prices/flags and eligible daily components.
# Output: one coverage/price figure and one signed-decomposition figure.
missing_days <- country_days %>% filter(!row_observed)
changing_days <- country_days %>% filter(vendor_set_change_pair)
check(nrow(missing_days) == 3 && nrow(changing_days) == 73,
      "Figure annotations do not reconcile with gap and changing-set counts.")
price_plot_data <- bind_rows(
  country_days %>%
    transmute(country_id, country_name, date,
              series = "Recorded weighted price",
              recorded_price_usd = if_else(country_day_valid,
                                           source_combined_price_usd, NA_real_)),
  vendor_days %>%
    transmute(country_id, country_name, date, series = vendor,
              recorded_price_usd = if_else(country_day_valid & positive_stock,
                                           price_usd, NA_real_))
) %>%
  arrange(country_id, series, date) %>%
  group_by(country_id, series) %>%
  mutate(line_segment = cumsum(is.na(recorded_price_usd))) %>%
  ungroup() %>%
  filter(!is.na(recorded_price_usd))
check(sum(price_plot_data$series == "Recorded weighted price") == 1080,
      "The price figure does not contain all 1,080 observed weighted prices.")

recorded_prices_figure <- ggplot(
  price_plot_data,
  aes(x = date, y = recorded_price_usd, colour = series,
      group = interaction(series, line_segment))
) +
  geom_line(linewidth = 0.45) +
  geom_vline(data = missing_days, aes(xintercept = date),
             inherit.aes = FALSE, linetype = "dashed", colour = "#B22222",
             linewidth = 0.5) +
  geom_point(data = changing_days,
             aes(x = date, y = source_combined_price_usd),
             inherit.aes = FALSE, shape = 21, fill = "white",
             colour = "black", size = 1.4, stroke = 0.5) +
  facet_grid(country_name ~ ., scales = "free_y") +
  scale_colour_manual(values = c(
    "Recorded weighted price" = "black", "SMSPVA" = "#2C7FB8",
    "SMSHub" = "#41AB5D", "SMS-Activate" = "#D95F0E", "5SIM" = "#88419D"
  )) +
  scale_x_date(date_breaks = "2 months", date_labels = "%Y-%m") +
  labs(title = "Recorded Facebook verification prices and coverage",
       x = NULL, y = "Recorded USD per verification", colour = NULL,
       caption = "Lines stop when a price is unavailable. Red dashed: missing source day; open circle: vendor set changed versus previous day.\nPositive-stock vendor quotes only; country denotes phone-number market.") +
  theme_minimal(base_size = 11) +
  theme(legend.position = "bottom")

decomposition_plot_data <- pair_components %>%
  select(country_id, country_name, date, price_component_usd,
         weight_component_usd, observed_net_change_usd) %>%
  pivot_longer(cols = c(price_component_usd, weight_component_usd,
                        observed_net_change_usd),
               names_to = "series", values_to = "daily_change_usd") %>%
  mutate(series = recode(series,
                         price_component_usd = "Price component",
                         weight_component_usd = "Weight component",
                         observed_net_change_usd = "Observed net change"))
check(nrow(decomposition_plot_data) == 3 * 1001,
      "The decomposition figure does not contain all three values per eligible pair.")
decomposition_figure <- ggplot(decomposition_plot_data,
                               aes(x = date, y = daily_change_usd,
                                   colour = series)) +
  geom_hline(yintercept = 0, colour = "grey45", linewidth = 0.35) +
  geom_vline(data = changing_days, aes(xintercept = date),
             inherit.aes = FALSE, colour = "grey65", alpha = 0.18) +
  geom_vline(data = missing_days, aes(xintercept = date),
             inherit.aes = FALSE, linetype = "dashed", colour = "#B22222",
             linewidth = 0.5) +
  geom_point(size = 0.75, alpha = 0.7) +
  facet_grid(country_name ~ ., scales = "free_y") +
  scale_colour_manual(values = c("Price component" = "#2C7FB8",
                                 "Weight component" = "#D95F0E",
                                 "Observed net change" = "black")) +
  scale_x_date(date_breaks = "2 months", date_labels = "%Y-%m") +
  labs(title = "Daily recorded weighted-price decomposition: eligible pairs only",
       x = NULL, y = "Signed change in recorded USD per verification",
       colour = NULL,
       caption = "Points are eligible adjacent-day pairs; no line connects excluded dates. Pale vertical: vendor-set change; red dashed: missing source day.") +
  theme_minimal(base_size = 11) +
  theme(legend.position = "bottom")

# 5. Export tables and figures; re-read table row counts.
dir.create(table_dir, showWarnings = FALSE, recursive = TRUE)
dir.create(figure_dir, showWarnings = FALSE, recursive = TRUE)
pair_file <- file.path(table_dir, "daily_decomposition.csv")
summary_file <- file.path(table_dir, "primary_summary.csv")
selection_file <- file.path(table_dir, "vendor_set_selection_check.csv")
prices_figure_file <- file.path(figure_dir, "recorded_prices_coverage.png")
decomposition_figure_file <- file.path(figure_dir, "daily_decomposition.png")
write_csv(pair_components, pair_file)
write_csv(primary_summary, summary_file)
write_csv(selection_check, selection_file)
ggsave(prices_figure_file, recorded_prices_figure, width = 11, height = 8,
       units = "in", dpi = 300)
ggsave(decomposition_figure_file, decomposition_figure, width = 11, height = 8,
       units = "in", dpi = 300)
check(nrow(read_csv(pair_file, show_col_types = FALSE)) == 1001 &&
        nrow(read_csv(summary_file, show_col_types = FALSE)) == 3 &&
        nrow(read_csv(selection_file, show_col_types = FALSE)) == 6,
      "An analysis output table did not re-read with its expected row count.")
check(file.exists(prices_figure_file) && file.exists(decomposition_figure_file),
      "An analysis figure was not saved.")
cat("\nANALYSIS COMPLETE; REVIEW SAVED OUTPUTS\n")
cat("Tables:\n", pair_file, "\n", summary_file, "\n", selection_file, "\n")
cat("Figures:\n", prices_figure_file, "\n", decomposition_figure_file, "\n")
cat("Review mean versus median and maximum for unusually large days; signed components for offsets;\n")
cat("and changing-set movement share for the scope of excluded pairs. Do not infer sales, demand, or causation.\n")

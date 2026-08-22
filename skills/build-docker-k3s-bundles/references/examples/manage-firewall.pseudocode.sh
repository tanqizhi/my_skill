#!/usr/bin/env bash
# REFERENCE PSEUDOCODE ONLY.
# This file is intentionally non-executable design documentation.
# Do not run it, remove this guard, copy it into a bundle, or translate its
# placeholders directly into privileged commands. Generate and test a
# backend-specific module after discovering ownership and live node state.

printf '%s\n' 'REFERENCE ONLY: manage-firewall.pseudocode.sh must not be executed.' >&2
exit 64

set -Eeuo pipefail

# Unreachable pseudocode begins here.

load_firewall_context() {
  # Read desired NAT rules, node inventory, installed bundle directory,
  # non-interactive policy, saved ownership metadata, and previous snapshots.
  manifest_load
  node_inventory_load
  firewall_state_load
}

discover_node() {
  local node_name=${1:?node name required}
  local node_ip=${2:?node IP required}

  # Detect iptables-legacy, iptables-nft, native nftables, and firewalld
  # ownership. Read nat/PREROUTING, same-name chains, jumps, comments,
  # persistence configuration, duplicates, and current rule order.
  remote_adapter_discover_firewall "${node_name}" "${node_ip}"
}

select_or_reuse_owned_chain() {
  # Reuse the exact existing chain name and jump position only when ownership
  # and semantics are verified. Create nothing when ownership is ambiguous.
  case "$(firewall_classify_existing_chain)" in
    compatible)
      firewall_plan_adopt_existing_chain
      firewall_plan_add_only_missing_owned_entries
      ;;
    absent)
      firewall_plan_create_owned_chain_and_single_jump
      ;;
    ambiguous|incompatible|duplicate-jump)
      firewall_print_conflict
      return 1
      ;;
  esac
}

build_ordered_crud_plan() {
  local action=${1:?action required}
  local rule_id=${2:-}
  local position=${3:-}

  # action is one of: list, add, update, delete, status, sync, repair.
  # position is beginning, end, before:<rule-id>, or after:<rule-id>.
  # Build an ordered desired ruleset using stable bundle-owned rule IDs.
  firewall_plan_build "${action}" "${rule_id}" "${position}"
  firewall_plan_reject_foreign_rule_changes
  firewall_plan_print_diff
}

snapshot_and_apply_node() {
  local node_name=${1:?node name required}
  local node_ip=${2:?node IP required}

  remote_adapter_snapshot_owned_firewall "${node_name}" "${node_ip}"
  remote_adapter_apply_owned_firewall_atomically "${node_name}" "${node_ip}"
  remote_adapter_verify_chain_jump_order_and_hash "${node_name}" "${node_ip}"
}

print_local_recovery_command() {
  local node_name=${1:?node name required}
  local node_ip=${2:?node IP required}
  local installed_dir=${3:?installed directory required}
  local command

  # The real module must render actual values and shell-escape installed_dir.
  printf -v command 'cd %q && sudo ./manage.sh firewall sync --local-node --non-interactive' "${installed_dir}"
  printf 'Failed node: %s (%s)\n' "${node_name}" "${node_ip}"
  printf 'Run locally on that node: %s\n' "${command}"
}

handle_node_failure() {
  local node_name=${1:?node name required}
  local node_ip=${2:?node IP required}
  local installed_dir=${3:?installed directory required}

  firewall_print_redacted_failure "${node_name}" "${node_ip}"
  print_local_recovery_command "${node_name}" "${node_ip}" "${installed_dir}"

  if execution_is_non_interactive; then
    # Stop unless the caller explicitly supplied continue or rollback.
    decision="$(require_explicit_on_node_failure_policy)"
  else
    decision="$(ui_select continue rollback)"
  fi

  case "${decision}" in
    continue)
      firewall_state_record_partial_failure "${node_name}" "${node_ip}"
      return 0
      ;;
    rollback)
      rollback_every_node_changed_by_current_operation
      report_refresh_deployment_and_operations
      return 1
      ;;
    *)
      return 1
      ;;
  esac
}

sync_every_cluster_node() {
  local installed_dir=${1:?installed directory required}

  # Run read-only preflight on every declared server and agent before the first
  # mutation. A real implementation must not silently omit unreachable nodes.
  for_each_declared_node discover_node
  firewall_plan_require_all_preflight_results

  while node_inventory_next node_name node_ip node_role; do
    if ! snapshot_and_apply_node "${node_name}" "${node_ip}"; then
      handle_node_failure "${node_name}" "${node_ip}" "${installed_dir}" || return 1
    fi
  done

  firewall_compare_desired_hash_on_every_node
  firewall_state_record_cluster_result
  report_refresh_deployment_and_operations
}

interactive_firewall_menu() {
  load_firewall_context
  action="$(ui_select list add update delete status sync repair back)"
  [[ "${action}" == back ]] && return 0

  # For mutation, collect stable rule ID and insertion position, show exact
  # ordered diff, request privilege authorization, then apply to one node or
  # synchronize every declared cluster node.
  build_ordered_crud_plan "${action}" "${rule_id:-}" "${position:-}"
  authorization_require_confirmation_if_mutating "${action}"
  sync_every_cluster_node "${installed_bundle_dir}"
}

# The real generated module would call its validated entrypoint here.
# interactive_firewall_menu

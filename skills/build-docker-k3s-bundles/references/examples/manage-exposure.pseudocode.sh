#!/usr/bin/env bash
# REFERENCE PSEUDOCODE ONLY.
# This file is intentionally non-executable design documentation.
# Do not run it, remove this guard, copy it into a bundle, or treat adapter
# names below as implemented commands. Generate and test a target-specific
# management module from the bundle manifest and observed runtime instead.

printf '%s\n' 'REFERENCE ONLY: manage-exposure.pseudocode.sh must not be executed.' >&2
exit 64

set -Eeuo pipefail

# Unreachable pseudocode begins here.

load_context() {
  # Read the bundle manifest, generated-file ownership metadata, installation
  # state, user overrides, deployment target, and authorization mode.
  manifest_load
  state_load
  ownership_load
}

discover_actual_exposure() {
  local target=${1:?target required}

  case "${target}" in
    docker)
      # Discover effective Compose/runtime mappings, not only desired YAML.
      docker_adapter_discover_published_ports
      ;;
    k3s)
      # Discover the effective cluster NodePort range, Services, protocols,
      # endpoints, and current allocations.
      k3s_adapter_discover_nodeports
      ;;
    *)
      return 64
      ;;
  esac
}

build_change_plan() {
  local target=${1:?target required}
  local action=${2:?action required}
  local object_id=${3:-}

  # action is one of: list, add, update, delete.
  # Collect runtime-specific fields, validate ownership, reject host-port or
  # NodePort conflicts, and compute only the affected generated resources.
  exposure_plan_build "${target}" "${action}" "${object_id}"
  exposure_plan_validate
}

preview_and_confirm() {
  # Show the old and new ordered mappings, affected services, restart or patch
  # scope, reachability impact, rollback source, and exact planned operations.
  exposure_plan_print_diff
  authorization_require_confirmation
}

apply_with_rollback() {
  local target=${1:?target required}

  exposure_backup_create

  case "${target}" in
    docker)
      # Rewrite only owned generated configuration, then recreate only affected
      # services. Never overwrite user-managed Compose fragments.
      docker_adapter_apply_owned_mapping
      docker_adapter_reconcile_affected_services
      ;;
    k3s)
      # Patch only the intended Service after recording the complete live object.
      k3s_adapter_apply_nodeport
      ;;
  esac

  if ! exposure_adapter_verify_mapping_and_health "${target}"; then
    exposure_backup_restore
    exposure_adapter_verify_rollback "${target}"
    return 1
  fi

  manifest_update_desired_exposure
  state_record_observed_exposure
  report_refresh_deployment_and_operations
}

interactive_exposure_menu() {
  load_context

  while true; do
    target="$(ui_select docker k3s back)"
    [[ "${target}" == back ]] && return 0

    discover_actual_exposure "${target}"
    action="$(ui_select list add update delete back)"
    [[ "${action}" == back ]] && continue

    if [[ "${action}" == list ]]; then
      exposure_print_desired_and_actual "${target}"
      continue
    fi

    object_id="$(ui_select_owned_or_new_object "${target}" "${action}")"
    build_change_plan "${target}" "${action}" "${object_id}"
    preview_and_confirm
    apply_with_rollback "${target}"
  done
}

# The real generated module would call its validated entrypoint here.
# interactive_exposure_menu

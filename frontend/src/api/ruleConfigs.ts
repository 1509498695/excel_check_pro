import type {
  RuleConfigCredentialsStatusResponse,
  RuleConfigCreateRequest,
  RuleConfigListResponse,
  RuleConfigMutationRequest,
  RuleConfigRecordResponse,
  RuleConfigRollbackRequest,
  RuleConfigTrialRequest,
  RuleConfigTrialResponse,
  RuleConfigValidationResponse,
  RuleConfigVersionsResponse,
  RuleFamily,
} from '../types/ruleConfigs'
import { RULE_FAMILY_CONFIG_LOOKUP } from '../types/ruleConfigs'
import { apiFetch } from '../utils/apiFetch'

function ruleConfigPath(ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP): string {
  return `/api/v1/rule-configs/${ruleFamily}`
}

function ruleConfigRecordPath(
  ruleId: number | string,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): string {
  return `${ruleConfigPath(ruleFamily)}/${ruleId}`
}

function buildMutationBody(payload: RuleConfigMutationRequest): string {
  return JSON.stringify({
    content_md: payload.contentMd,
    expected_optimistic_lock_version: payload.baseVersion,
    description: payload.description ?? '',
  })
}

export async function apiListRuleConfigs(
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigListResponse> {
  return apiFetch<RuleConfigListResponse>(ruleConfigPath(ruleFamily))
}

export async function apiCreateRuleConfig(
  payload: RuleConfigCreateRequest,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigRecordResponse> {
  return apiFetch<RuleConfigRecordResponse>(ruleConfigPath(ruleFamily), {
    method: 'POST',
    body: JSON.stringify({
      content_md: payload.contentMd,
      description: payload.description ?? '',
    }),
  })
}

export async function apiGetRuleConfig(
  ruleId: number | string,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigRecordResponse> {
  return apiFetch<RuleConfigRecordResponse>(ruleConfigRecordPath(ruleId, ruleFamily))
}

export async function apiDeleteRuleConfig(
  ruleId: number | string,
  baseVersion: number,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<void> {
  const params = new URLSearchParams({
    expected_optimistic_lock_version: String(baseVersion),
  })
  return apiFetch<void>(`${ruleConfigRecordPath(ruleId, ruleFamily)}?${params.toString()}`, {
    method: 'DELETE',
  })
}

export async function apiListRuleConfigVersions(
  ruleId: number | string,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigVersionsResponse> {
  return apiFetch<RuleConfigVersionsResponse>(`${ruleConfigRecordPath(ruleId, ruleFamily)}/versions`)
}

export async function apiValidateRuleConfig(
  ruleId: number | string,
  contentMd: string,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigValidationResponse> {
  return apiFetch<RuleConfigValidationResponse>(`${ruleConfigRecordPath(ruleId, ruleFamily)}/validate`, {
    method: 'POST',
    body: JSON.stringify({ content_md: contentMd }),
  })
}

export async function apiTrialRuleConfig(
  ruleId: number | string,
  payload: RuleConfigTrialRequest,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigTrialResponse> {
  return apiFetch<RuleConfigTrialResponse>(`${ruleConfigRecordPath(ruleId, ruleFamily)}/trial`, {
    method: 'POST',
    body: JSON.stringify({
      query_type: payload.queryType,
      versioned_config_folder: payload.versionedConfigFolder,
      lookup_input: payload.lookupInput,
      use_current_draft: payload.useCurrentDraft,
      content_md: payload.contentMd,
    }),
  })
}

export async function apiSaveRuleConfigDraft(
  ruleId: number | string,
  payload: RuleConfigMutationRequest,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigRecordResponse> {
  return apiFetch<RuleConfigRecordResponse>(`${ruleConfigRecordPath(ruleId, ruleFamily)}/draft`, {
    method: 'PUT',
    body: buildMutationBody(payload),
  })
}

export async function apiPublishRuleConfig(
  ruleId: number | string,
  payload: RuleConfigMutationRequest,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigRecordResponse> {
  return apiFetch<RuleConfigRecordResponse>(`${ruleConfigRecordPath(ruleId, ruleFamily)}/publish`, {
    method: 'POST',
    body: buildMutationBody(payload),
  })
}

export async function apiRollbackRuleConfigVersion(
  ruleId: number | string,
  version: number,
  payload: RuleConfigRollbackRequest,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigRecordResponse> {
  return apiFetch<RuleConfigRecordResponse>(
    `${ruleConfigRecordPath(ruleId, ruleFamily)}/versions/${version}/rollback`,
    {
      method: 'POST',
      body: JSON.stringify({
        expected_optimistic_lock_version: payload.baseVersion,
        description: payload.description ?? '',
      }),
    },
  )
}

export async function apiGetRuleConfigCredentialsStatus(
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigCredentialsStatusResponse> {
  return apiFetch<RuleConfigCredentialsStatusResponse>(
    `${ruleConfigPath(ruleFamily)}/credentials/status`,
  )
}

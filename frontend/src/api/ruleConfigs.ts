import type {
  RuleConfigCredentialsStatusResponse,
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

function buildMutationBody(payload: RuleConfigMutationRequest): string {
  return JSON.stringify({
    content_md: payload.contentMd,
    expected_optimistic_lock_version: payload.baseVersion,
    description: payload.description ?? '',
  })
}

export async function apiGetRuleConfig(
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigRecordResponse> {
  return apiFetch<RuleConfigRecordResponse>(ruleConfigPath(ruleFamily))
}

export async function apiListRuleConfigVersions(
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigVersionsResponse> {
  return apiFetch<RuleConfigVersionsResponse>(`${ruleConfigPath(ruleFamily)}/versions`)
}

export async function apiValidateRuleConfig(
  contentMd: string,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigValidationResponse> {
  return apiFetch<RuleConfigValidationResponse>(`${ruleConfigPath(ruleFamily)}/validate`, {
    method: 'POST',
    body: JSON.stringify({ content_md: contentMd }),
  })
}

export async function apiTrialRuleConfig(
  payload: RuleConfigTrialRequest,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigTrialResponse> {
  return apiFetch<RuleConfigTrialResponse>(`${ruleConfigPath(ruleFamily)}/trial`, {
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
  payload: RuleConfigMutationRequest,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigRecordResponse> {
  return apiFetch<RuleConfigRecordResponse>(`${ruleConfigPath(ruleFamily)}/draft`, {
    method: 'PUT',
    body: buildMutationBody(payload),
  })
}

export async function apiPublishRuleConfig(
  payload: RuleConfigMutationRequest,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigRecordResponse> {
  return apiFetch<RuleConfigRecordResponse>(`${ruleConfigPath(ruleFamily)}/publish`, {
    method: 'POST',
    body: buildMutationBody(payload),
  })
}

export async function apiRollbackRuleConfigVersion(
  version: number,
  payload: RuleConfigRollbackRequest,
  ruleFamily: RuleFamily | string = RULE_FAMILY_CONFIG_LOOKUP,
): Promise<RuleConfigRecordResponse> {
  return apiFetch<RuleConfigRecordResponse>(
    `${ruleConfigPath(ruleFamily)}/versions/${version}/rollback`,
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

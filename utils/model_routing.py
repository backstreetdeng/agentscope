"""User-approved model policy: Flash by default, Pro for complex agent tasks."""
from copy import deepcopy
import re

DEFAULT_PROVIDER='deepseek_flash'
COMPLEX_PROVIDER='deepseek_pro'
COMPLEX_PATTERN=re.compile(r'三情景|多情景|多因素|跨模块|联合分析|冲突核验|情景.*对比|对比.*情景|政策.*(?:组合|叠加)|复杂任务')


def route_model(config, *, question='', complex_task=False, requested=None):
    result=deepcopy(config)
    if requested:
        provider=requested
    else:
        provider=COMPLEX_PROVIDER if complex_task or COMPLEX_PATTERN.search(question) else DEFAULT_PROVIDER
    definition=result.get('providers',{}).get(provider)
    if not definition or definition.get('enabled') is False:
        raise ValueError('所选模型未配置或已停用：'+provider)
    result['active_provider']=provider
    return result

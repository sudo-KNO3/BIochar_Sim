'''
Sensitivity Analysis Module for Option B

Sweeps key parameters to find viable operating regions.
Outputs CSV data and heatmap visualizations.
'''

from dataclasses import dataclass, replace
from typing import List, Tuple, Dict, Optional
import csv
import os
from pathlib import Path

from ..core.parameters import (
    ModelParameters,
    create_option_b_scenario,
    EconomicParams,
    CofeedSupplyParams,
    CharQualityParams,
    CapexScalingParams,
)
from ..simulation.deterministic import run_stage1_option_b, ViabilityStatus


@dataclass
class SensitivityPoint:
    '''Single point in sensitivity sweep.'''
    param1_value: float
    param2_value: float
    noi: float
    self_sufficiency: float
    payback_years: float
    status: str


@dataclass
class SensitivityResult:
    '''Result of 2D sensitivity sweep.'''
    param1_name: str
    param2_name: str
    param1_values: List[float]
    param2_values: List[float]
    points: List[SensitivityPoint]
    viable_count: int
    marginal_count: int
    not_viable_count: int


def run_1d_sweep(
    base_params: ModelParameters,
    param_name: str,
    values: List[float],
    param_setter: callable,
) -> List[Tuple[float, float, float, str]]:
    '''
    Run 1D sensitivity sweep.
    
    Returns list of (value, noi, self_sufficiency, status) tuples.
    '''
    results = []
    for v in values:
        params = param_setter(base_params, v)
        result = run_stage1_option_b(params)
        results.append((
            v,
            result.economics.annual_noi,
            result.energy.energy_self_sufficiency,
            result.overall_status.name
        ))
    return results


def run_2d_sweep(
    base_params: ModelParameters,
    param1_name: str,
    param1_values: List[float],
    param1_setter: callable,
    param2_name: str,
    param2_values: List[float],
    param2_setter: callable,
) -> SensitivityResult:
    '''
    Run 2D sensitivity sweep for heatmap generation.
    '''
    points = []
    viable_count = 0
    marginal_count = 0
    not_viable_count = 0
    
    for v1 in param1_values:
        params_1 = param1_setter(base_params, v1)
        for v2 in param2_values:
            params_2 = param2_setter(params_1, v2)
            result = run_stage1_option_b(params_2)
            
            status = result.overall_status.name
            if result.overall_status == ViabilityStatus.VIABLE:
                viable_count += 1
            elif result.overall_status == ViabilityStatus.MARGINAL:
                marginal_count += 1
            else:
                not_viable_count += 1
            
            points.append(SensitivityPoint(
                param1_value=v1,
                param2_value=v2,
                noi=result.economics.annual_noi,
                self_sufficiency=result.energy.energy_self_sufficiency,
                payback_years=result.economics.simple_payback_years,
                status=status,
            ))
    
    return SensitivityResult(
        param1_name=param1_name,
        param2_name=param2_name,
        param1_values=param1_values,
        param2_values=param2_values,
        points=points,
        viable_count=viable_count,
        marginal_count=marginal_count,
        not_viable_count=not_viable_count,
    )


# Parameter setters
def set_tipping_fee(params: ModelParameters, value: float) -> ModelParameters:
    new_economic = replace(params.economic, tipping_fee_per_m3=value)
    return replace(params, economic=new_economic)


def set_char_tier2_price(params: ModelParameters, value: float) -> ModelParameters:
    new_char = replace(params.char_quality, tier_2_price=value)
    return replace(params, char_quality=new_char)


def set_cofeed_volume(params: ModelParameters, value: float) -> ModelParameters:
    new_supply = replace(params.cofeed_supply, annual_target_tds=value)
    return replace(params, cofeed_supply=new_supply)


def set_labor_factor(params: ModelParameters, value: float) -> ModelParameters:
    '''Scales labor cost by adjusting operators_per_shift.'''
    new_economic = replace(params.economic, operators_per_shift=1.5 * value)
    return replace(params, economic=new_economic)


def set_complexity_factor(params: ModelParameters, value: float) -> ModelParameters:
    new_capex = replace(params.capex_scaling, operator_complexity_factor=value)
    return replace(params, capex_scaling=new_capex)


def export_sensitivity_csv(result: SensitivityResult, output_dir: str) -> str:
    '''Export sensitivity results to CSV.'''
    os.makedirs(output_dir, exist_ok=True)
    filename = f'{result.param1_name}_vs_{result.param2_name}.csv'
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            result.param1_name, result.param2_name,
            'NOI', 'Self_Sufficiency', 'Payback_Years', 'Status'
        ])
        for p in result.points:
            writer.writerow([
                p.param1_value, p.param2_value,
                p.noi, p.self_sufficiency, p.payback_years, p.status
            ])
    
    return filepath


def run_standard_sensitivity(
    output_dir: str = 'sensitivity',
    n_steps: int = 10
) -> Dict[str, SensitivityResult]:
    '''
    Run standard sensitivity sweeps for Option B viability.
    
    Key sweeps:
    1. Tipping fee vs char price
    2. Co-feed volume vs labor factor
    3. Tipping fee vs co-feed volume
    
    Returns dict of SensitivityResult keyed by sweep name.
    '''
    base_params = create_option_b_scenario()
    results = {}
    
    # Define value ranges
    tipping_fees = [v for v in range(30, 105, int(70/n_steps))][:n_steps]
    char_prices = [v for v in range(100, 405, int(300/n_steps))][:n_steps]
    cofeed_volumes = [v for v in range(600, 2405, int(1800/n_steps))][:n_steps]
    labor_factors = [0.5 + i * 0.1 for i in range(n_steps)]
    
    print(f'Tipping fees: {tipping_fees}')
    print(f'Char prices: {char_prices}')
    print(f'Cofeed volumes: {cofeed_volumes}')
    print(f'Labor factors: {labor_factors}')
    
    # Sweep 1: Tipping fee vs char Tier 2 price
    print('Running sweep: Tipping vs Char Price...')
    result = run_2d_sweep(
        base_params,
        'tipping_fee', tipping_fees, set_tipping_fee,
        'char_tier2_price', char_prices, set_char_tier2_price,
    )
    results['tipping_vs_char'] = result
    export_sensitivity_csv(result, output_dir)
    print(f'  Viable: {result.viable_count}, Marginal: {result.marginal_count}, Not Viable: {result.not_viable_count}')
    
    # Sweep 2: Co-feed volume vs labor factor
    print('Running sweep: Cofeed Volume vs Labor Factor...')
    result = run_2d_sweep(
        base_params,
        'cofeed_volume_tds', cofeed_volumes, set_cofeed_volume,
        'labor_factor', labor_factors, set_labor_factor,
    )
    results['cofeed_vs_labor'] = result
    export_sensitivity_csv(result, output_dir)
    print(f'  Viable: {result.viable_count}, Marginal: {result.marginal_count}, Not Viable: {result.not_viable_count}')
    
    # Sweep 3: Tipping fee vs co-feed volume
    print('Running sweep: Tipping vs Cofeed Volume...')
    result = run_2d_sweep(
        base_params,
        'tipping_fee', tipping_fees, set_tipping_fee,
        'cofeed_volume_tds', cofeed_volumes, set_cofeed_volume,
    )
    results['tipping_vs_cofeed'] = result
    export_sensitivity_csv(result, output_dir)
    print(f'  Viable: {result.viable_count}, Marginal: {result.marginal_count}, Not Viable: {result.not_viable_count}')
    
    return results


def find_breakeven_points(result: SensitivityResult) -> List[SensitivityPoint]:
    '''Find points near breakeven (NOI close to 0).'''
    breakevens = []
    for p in result.points:
        if -20000 < p.noi < 20000:  # Within  of breakeven
            breakevens.append(p)
    return breakevens


if __name__ == '__main__':
    print('Running Option B Sensitivity Analysis...')
    results = run_standard_sensitivity(n_steps=10)
    
    for name, result in results.items():
        print(f'\\n=== {name} ===')
        breakevens = find_breakeven_points(result)
        print(f'Breakeven points found: {len(breakevens)}')
        for bp in breakevens[:5]:
            print(f'  {result.param1_name}={bp.param1_value}, {result.param2_name}={bp.param2_value} -> NOI={bp.noi:,.0f}')

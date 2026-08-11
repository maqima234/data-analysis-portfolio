"""
AB 测试：支付宝营销策略效果评估
对照组(1) vs 实验组(2)，比较广告点击率差异
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False
from scipy.stats import chi2_contingency, norm
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 数据加载
# ============================================================
print('数据加载...')

df = pd.read_csv(
    r'C:\Users\86186\Desktop\audience_expansion\effect_tb.csv',
    header=None,
    names=['dmp_id', 'user_id', 'click', 'flag']
)

n_control = (df['dmp_id'] == 1).sum()
n_treat   = (df['dmp_id'] == 2).sum()
click_c   = (df[df['dmp_id'] == 1]['click'] == 1).sum()
click_t   = (df[df['dmp_id'] == 2]['click'] == 1).sum()
rate_c    = click_c / n_control
rate_t    = click_t / n_treat

print(f'对照组: {n_control:,} 人, 点击 {click_c:,}, 点击率 {rate_c*100:.2f}%')
print(f'实验组: {n_treat:,} 人, 点击 {click_t:,}, 点击率 {rate_t*100:.2f}%')
print(f'提升幅度: {(rate_t - rate_c)*100:.2f} 个百分点 ({(rate_t/rate_c - 1)*100:.1f}%)')

# ============================================================
# 卡方检验
# ============================================================
print('\n卡方检验...')

# 列联表
contingency = pd.crosstab(df['dmp_id'], df['click'])
print(contingency)

chi2, p_value, dof, expected = chi2_contingency(contingency)
print(f'\n卡方值: {chi2:.2f}')
print(f'p 值:  {p_value:.2e}')
print(f'结论: {"显著" if p_value < 0.05 else "不显著"} (alpha=0.05)')

# ============================================================
# 置信区间
# ============================================================
print('\n置信区间计算...')

diff = rate_t - rate_c
se = np.sqrt(rate_c*(1-rate_c)/n_control + rate_t*(1-rate_t)/n_treat)
ci_lower = diff - 1.96 * se
ci_upper = diff + 1.96 * se

print(f'点击率差异: {diff*100:.4f} 个百分点')
print(f'95% 置信区间: [{ci_lower*100:.4f}%, {ci_upper*100:.4f}%]')
print(f'结论: {"差异显著（区间不含0）" if ci_lower > 0 else "差异不显著（区间含0）"}')

# ============================================================
# 可视化
# ============================================================
print('\n生成可视化...')

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 点击率对比
rates = [rate_c*100, rate_t*100]
labels = [f'对照组\n({rate_c*100:.2f}%)', f'实验组\n({rate_t*100:.2f}%)']
colors = ['steelblue', 'darkorange']
bars = axes[0].bar(labels, rates, color=colors, width=0.4)
for bar, rate in zip(bars, rates):
    axes[0].text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.02,
                 f'{rate:.2f}%', ha='center', fontsize=14, fontweight='bold')
axes[0].set_ylabel('点击率 (%)')
axes[0].set_title('对照组 vs 实验组 点击率对比')
axes[0].set_ylim(0, max(rates)*1.3)

# 置信区间
axes[1].errorbar(['点击率差异'], [diff*100], yerr=[[(diff-ci_lower)*100], [(ci_upper-diff)*100]],
                 fmt='o', color='darkorange', capsize=10, markersize=10, linewidth=2)
axes[1].axhline(y=0, color='gray', linestyle='--')
axes[1].set_ylabel('点击率差异 (百分点)')
axes[1].set_title(f'效应量估计 (95% CI)\np = {p_value:.2e}')
axes[1].annotate(f'{diff*100:.4f}%', xy=(0, diff*100), xytext=(0.15, diff*100+0.01),
                fontsize=12, fontweight='bold')

plt.tight_layout()
plt.savefig('ab_test_result.png', dpi=150)
plt.close()

# ============================================================
# 总结
# ============================================================
print('\n' + '='*60)
print('AB 测试结论')
print('='*60)
print(f'实验组点击率: {rate_t*100:.2f}%')
print(f'对照组点击率: {rate_c*100:.2f}%')
print(f'差异: {diff*100:.4f} 个百分点 ({(rate_t/rate_c-1)*100:.1f}%)')
print(f'p 值: {p_value:.2e} ({"" if p_value < 0.05 else "不"}显著)')
print(f'95% CI: [{ci_lower*100:.4f}%, {ci_upper*100:.4f}%]')
print(f'\n建议: {"全量上线实验组策略" if p_value < 0.05 and diff > 0 else "暂不上线"}')

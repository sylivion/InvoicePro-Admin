# -*- coding: utf-8 -*-
import sys
import os
import shutil

sys.stdout.reconfigure(encoding='utf-8')

# Read AdminPanel.html
with open('AdminPanel.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Global fix for escaped backslash quotes in HTML attributes
content = content.replace(r'\"fmtCurrency(', '"fmtCurrency(')
content = content.replace(r')\"', ')"')

# 2. Modern, beautiful Revenue View HTML
modern_revenue_html = '''    <main class="flex-1 overflow-y-auto p-6" x-show="view==='revenue' && canAccess('revenue')" x-cloak>
      <div class="space-y-6">
        
        <!-- Header -->
        <div class="flex items-center justify-between flex-wrap gap-3">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-emerald-50 dark:bg-emerald-950/70 border border-emerald-200/70 dark:border-emerald-800/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center text-lg shadow-xs flex-shrink-0">
              <i class="fa-solid fa-chart-line"></i>
            </div>
            <div>
              <h1 class="text-xl font-bold text-slate-900 dark:text-white tracking-tight">Financial Revenue &amp; Analytics</h1>
              <p class="text-xs text-slate-500 dark:text-slate-400">Track software license earnings, performance trends, renewal forecasts, and city distribution</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs font-semibold text-slate-600 dark:text-slate-300 shadow-xs">
              <i class="fa-regular fa-calendar text-emerald-500"></i>
              <span x-text="'Updated: ' + new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })"></span>
            </span>
          </div>
        </div>

        <!-- ══ TOP ROW KPI CARDS ══ -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <!-- Total Revenue Card -->
          <div class="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200/80 dark:border-slate-800 shadow-xs col-span-2 relative overflow-hidden">
            <div class="flex items-center justify-between text-slate-400 mb-2">
              <span class="text-[11px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">Total Revenue Earned</span>
              <div class="w-8 h-8 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center text-sm">
                <i class="fa-solid fa-indian-rupee-sign"></i>
              </div>
            </div>
            <div class="text-3xl sm:text-4xl font-extrabold text-emerald-600 dark:text-emerald-400 font-mono tracking-tight" x-text="fmtCurrency(totalRevenue)"></div>
            <div class="text-xs text-slate-500 dark:text-slate-400 mt-1 flex items-center gap-2">
              <span>Cumulative Lifetime Revenue</span>
              <span>•</span>
              <span class="font-semibold text-slate-700 dark:text-slate-300" x-text="(filteredCustomers || []).length + ' Customers Closed'"></span>
            </div>
          </div>

          <!-- License Sales -->
          <div class="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200/80 dark:border-slate-800 shadow-xs col-span-2">
            <div class="flex items-center justify-between text-slate-400 mb-2">
              <span class="text-[11px] font-bold uppercase tracking-wider text-brand-600 dark:text-brand-400">License Sales Revenue</span>
              <div class="w-8 h-8 rounded-xl bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 flex items-center justify-center text-sm">
                <i class="fa-solid fa-receipt"></i>
              </div>
            </div>
            <div class="text-3xl sm:text-4xl font-extrabold text-brand-600 dark:text-brand-400 font-mono tracking-tight" x-text="fmtCurrency(licenseRevenue)"></div>
            <div class="text-xs text-slate-500 dark:text-slate-400 mt-1">Direct software package purchases</div>
          </div>
        </div>

        <!-- ══ PERFORMANCE TRENDS ROW (Best Month, This Month, 90-Day Forecast) ══ -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <!-- Best Month Ever -->
          <div class="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200/80 dark:border-slate-800 shadow-xs">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2.5">
                <div class="w-8 h-8 rounded-xl bg-amber-50 dark:bg-amber-950/70 border border-amber-200/60 dark:border-amber-800/50 flex items-center justify-center text-amber-500 text-sm">
                  <i class="fa-solid fa-trophy"></i>
                </div>
                <span class="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wide">Best Month Ever</span>
              </div>
            </div>
            <template x-if="bestMonth">
              <div>
                <div class="text-2xl sm:text-3xl font-bold text-amber-600 dark:text-amber-400 font-mono" x-text="fmtCurrency(bestMonth.amount)"></div>
                <div class="text-xs font-semibold text-slate-500 dark:text-slate-400 mt-1 flex items-center gap-1.5">
                  <i class="fa-regular fa-calendar-check text-amber-500"></i>
                  <span x-text="bestMonth.label"></span>
                </div>
              </div>
            </template>
            <template x-if="!bestMonth">
              <div class="text-sm text-slate-400 font-medium py-2">No sales recorded yet</div>
            </template>
          </div>

          <!-- This Month Performance -->
          <div class="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200/80 dark:border-slate-800 shadow-xs">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2.5">
                <div class="w-8 h-8 rounded-xl bg-emerald-50 dark:bg-emerald-950/70 border border-emerald-200/60 dark:border-emerald-800/50 flex items-center justify-center text-emerald-500 text-sm">
                  <i class="fa-solid fa-arrow-trend-up"></i>
                </div>
                <span class="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wide">This Month</span>
              </div>
            </div>
            <div class="text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white font-mono" x-text="fmtCurrency(revenueTrend.thisMonth)"></div>
            <div class="flex items-center gap-2 mt-1.5 flex-wrap">
              <span class="text-xs font-bold px-2 py-0.5 rounded-full inline-flex items-center gap-1"
                :class="revenueTrend.up ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/80 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800' : 'bg-red-100 text-red-700 dark:bg-red-950/80 dark:text-red-300 border border-red-200 dark:border-red-800'"
                x-text="(revenueTrend.up ? '▲ +' : '▼ ') + Math.abs(revenueTrend.pct) + '%'"></span>
              <span class="text-xs text-slate-500 dark:text-slate-400"
                x-text="'vs ₹' + revenueTrend.lastMonth.toLocaleString('en-IN') + ' last month'"></span>
            </div>
          </div>

          <!-- 90-Day Forecast -->
          <div class="bg-white dark:bg-slate-900 rounded-2xl p-5 border border-slate-200/80 dark:border-slate-800 shadow-xs">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2.5">
                <div class="w-8 h-8 rounded-xl bg-indigo-50 dark:bg-indigo-950/70 border border-indigo-200/60 dark:border-indigo-800/50 flex items-center justify-center text-indigo-500 text-sm">
                  <i class="fa-solid fa-binoculars"></i>
                </div>
                <span class="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wide">90-Day Renewal Forecast</span>
              </div>
            </div>
            <div class="text-2xl sm:text-3xl font-bold text-indigo-600 dark:text-indigo-400 font-mono" x-text="fmtCurrency(revenueForecast.total)"></div>
            <div class="text-xs text-slate-500 dark:text-slate-400 mt-1" x-text="revenueForecast.upcoming.length + ' upcoming renewals expected'"></div>
            <div x-show="revenueForecast.upcoming.length > 0" class="mt-2.5 space-y-1.5 border-t border-slate-100 dark:border-slate-800 pt-2">
              <template x-for="r in revenueForecast.upcoming.slice(0,3)" :key="r.name">
                <div class="flex items-center justify-between text-xs">
                  <span class="text-slate-700 dark:text-slate-300 font-semibold truncate max-w-[130px]" x-text="r.name"></span>
                  <span class="text-indigo-600 dark:text-indigo-400 font-mono font-bold" x-text="fmtCurrency(r.amount) + ' (' + r.days + 'd)'"></span>
                </div>
              </template>
            </div>
          </div>
        </div>

        <!-- ══ ALL CUSTOMERS REVENUE LEDGER ══ -->
        <div class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xs overflow-hidden">
          <div class="px-5 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between flex-wrap gap-2">
            <div class="flex items-center gap-2.5">
              <div class="w-2.5 h-2.5 rounded-full bg-emerald-500"></div>
              <h3 class="text-sm font-bold text-slate-800 dark:text-white uppercase tracking-wider">All Customers — Revenue Breakdown</h3>
            </div>
            <span class="text-xs font-mono font-semibold text-slate-500 dark:text-slate-400"
              x-text="(revenueRows || []).length + ' Customer Records'"></span>
          </div>

          <div x-show="customers.length===0" class="text-center py-12 text-slate-400 text-sm">
            <i class="fa-solid fa-folder-open text-3xl mb-2 block text-slate-300 dark:text-slate-700"></i>
            No customer revenue records found.
          </div>

          <div x-show="customers.length>0" class="overflow-x-auto">
            <table class="w-full text-sm border-collapse">
              <thead class="bg-slate-50/90 dark:bg-slate-800/90 text-xs sm:text-[13px] font-bold text-slate-700 dark:text-slate-200 uppercase tracking-wider border-b border-slate-200 dark:border-slate-700 select-none">
                <tr>
                  <th class="text-left px-4 py-3.5 whitespace-nowrap">Customer</th>
                  <th class="text-left px-4 py-3.5 whitespace-nowrap">Purchase Date</th>
                  <th class="text-right px-4 py-3.5 whitespace-nowrap">License Amount</th>
                  <th class="text-right px-4 py-3.5 whitespace-nowrap">Total Contributed</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100 dark:divide-slate-800/80">
                <template x-for="c in revenueRows" :key="c.id">
                  <tr @click="openDetail(c.id)" class="hover:bg-slate-50/70 dark:hover:bg-slate-800/50 transition-colors cursor-pointer">
                    <td class="px-4 py-3.5">
                      <div class="font-bold text-slate-900 dark:text-white text-sm sm:text-[15px]" x-text="c.name"></div>
                      <div class="text-xs text-slate-400 flex items-center gap-2 mt-0.5">
                        <span x-show="c.city" x-text="c.city"></span>
                        <span x-show="c.planLabel" class="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300" x-text="c.planLabel"></span>
                      </div>
                    </td>
                    <td class="px-4 py-3.5 text-xs font-mono text-slate-600 dark:text-slate-400" x-text="fmtDate(c.purchaseDate)"></td>
                    <td class="px-4 py-3.5 text-right font-mono font-bold text-emerald-600 dark:text-emerald-400 text-sm sm:text-[14px]"
                      x-text="c.purchaseAmount ? '₹' + Number(c.purchaseAmount).toLocaleString('en-IN') : '—'"></td>
                    <td class="px-4 py-3.5 text-right font-mono font-bold text-slate-900 dark:text-white text-sm sm:text-[15px]"
                      x-text="fmtCurrency(c._total || c.purchaseAmount || 0)"></td>
                  </tr>
                </template>
              </tbody>
              <tfoot class="bg-slate-50/90 dark:bg-slate-800/90 font-bold border-t-2 border-slate-200 dark:border-slate-700">
                <tr>
                  <td colspan="2" class="px-4 py-3 text-slate-700 dark:text-slate-200 text-xs uppercase tracking-wider">Total Revenue</td>
                  <td class="px-4 py-3 text-right text-emerald-600 font-mono text-sm sm:text-[15px]" x-text="fmtCurrency(licenseRevenue)"></td>
                  <td class="px-4 py-3 text-right text-slate-900 dark:text-white font-mono text-sm sm:text-[15px]" x-text="fmtCurrency(totalRevenue)"></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        <!-- ══ CITY ANALYTICS TABLE ══ -->
        <div class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xs overflow-hidden"
          x-show="cityAnalytics.length>0">
          <div class="px-5 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <h3 class="text-sm font-bold text-slate-800 dark:text-white uppercase tracking-wider flex items-center gap-2">
              <i class="fa-solid fa-map-location-dot text-brand-500"></i>
              <span>Revenue Distribution by City</span>
            </h3>
            <span class="text-xs font-mono text-slate-400" x-text="cityAnalytics.length + ' Cities'"></span>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-sm border-collapse">
              <thead class="bg-slate-50/90 dark:bg-slate-800/90 text-xs sm:text-[13px] font-bold text-slate-700 dark:text-slate-200 uppercase tracking-wider border-b border-slate-200 dark:border-slate-700 select-none">
                <tr>
                  <th class="text-left px-4 py-3.5 whitespace-nowrap">City / Region</th>
                  <th class="text-center px-4 py-3.5 whitespace-nowrap">Customers</th>
                  <th class="text-right px-4 py-3.5 whitespace-nowrap">Total Revenue</th>
                  <th class="text-right px-4 py-3.5 whitespace-nowrap">Revenue Share</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100 dark:divide-slate-800/80">
                <template x-for="row in cityAnalytics" :key="row.city">
                  <tr class="hover:bg-slate-50/70 dark:hover:bg-slate-800/50 transition-colors">
                    <td class="px-4 py-3.5 font-bold text-slate-800 dark:text-slate-200 text-sm sm:text-[14px]">
                      <span x-text="row.city || 'Unspecified'"></span>
                    </td>
                    <td class="px-4 py-3.5 text-center font-mono font-semibold text-slate-600 dark:text-slate-400" x-text="row.count"></td>
                    <td class="px-4 py-3.5 text-right font-mono font-bold text-emerald-600 dark:text-emerald-400 text-sm sm:text-[14px]"
                      x-text="fmtCurrency(row.revenue)"></td>
                    <td class="px-4 py-3.5 text-right">
                      <div class="flex items-center justify-end gap-2">
                        <div class="w-16 bg-slate-100 dark:bg-slate-800 rounded-full h-2 overflow-hidden hidden sm:block">
                          <div class="bg-brand-500 h-2 rounded-full"
                            :style="'width: ' + (totalRevenue ? Math.round(row.revenue/totalRevenue*100) : 0) + '%'"></div>
                        </div>
                        <span class="font-mono text-xs font-bold text-slate-700 dark:text-slate-300 min-w-[36px]"
                          x-text="totalRevenue ? Math.round(row.revenue/totalRevenue*100) + '%' : '0%'"></span>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </main>'''

start_tag = '<main class="flex-1 overflow-y-auto p-6" x-show="view===\'revenue\' && canAccess(\'revenue\')" x-cloak>'
end_tag = '<!-- ══ REMINDERS VIEW ══ -->'

start_idx = content.find(start_tag)
if start_idx == -1:
    print("Error: start_tag not found for revenue view!")
    sys.exit(1)

end_idx = content.find(end_tag, start_idx)
if end_idx == -1:
    print("Error: end_tag not found for revenue view!")
    sys.exit(1)

replacement = modern_revenue_html + "\n\n    "
new_content = content[:start_idx] + replacement + content[end_idx:]

with open('AdminPanel.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Updated AdminPanel.html successfully!")

print("Syncing to index.html...")
shutil.copyfile('AdminPanel.html', 'index.html')

sub_path = os.path.join('InvoicePro Admin', 'AdminPanel.html')
if os.path.exists(os.path.dirname(sub_path)):
    print(f"Syncing to {sub_path}...")
    shutil.copyfile('AdminPanel.html', sub_path)

print("All files synced successfully!")

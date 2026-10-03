# -*- coding: utf-8 -*-
import sys
import os
import shutil

sys.stdout.reconfigure(encoding='utf-8')

new_table_html = '''        <!-- Employees Table Container -->
        <div class="my-5 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xs overflow-hidden overflow-x-auto">
          <div x-show="employees.length===0" class="text-center py-12 text-sm text-slate-400">
            <i class="fa-solid fa-user-tie text-3xl mb-2 block text-slate-300 dark:text-slate-700"></i>
            No employees added yet.<br />
            <button @click="openAddEmployee()" class="text-brand-600 hover:underline text-xs mt-1 font-bold">Add your first employee →</button>
          </div>
          <table x-show="employees.length>0" class="w-full text-sm border-collapse min-w-[1280px]">
            <thead class="bg-slate-50/90 dark:bg-slate-800/90 text-xs sm:text-[13px] font-bold text-slate-700 dark:text-slate-200 uppercase tracking-wider border-b border-slate-200 dark:border-slate-700 select-none">
              <tr>
                <th class="px-3 py-3.5 w-12 text-center whitespace-nowrap">
                  <input type="checkbox" class="rounded cursor-pointer"
                    :checked="selectedEmps.length === filteredEmployees.length && filteredEmployees.length > 0"
                    :indeterminate="selectedEmps.length > 0 && selectedEmps.length < filteredEmployees.length"
                    @change="toggleSelectAllEmps($event.target.checked)" />
                </th>
                <th class="text-left px-4 py-3.5 whitespace-nowrap min-w-[130px]">EMP ID</th>
                <th class="text-left px-4 py-3.5 whitespace-nowrap min-w-[160px]">Name</th>
                <th class="text-left px-4 py-3.5 whitespace-nowrap min-w-[130px]">Mobile</th>
                <th class="text-left px-4 py-3.5 whitespace-nowrap min-w-[180px]">Designation / Dept</th>
                <th class="text-center px-4 py-3.5 whitespace-nowrap min-w-[130px]">Sales</th>
                <th class="text-right px-4 py-3.5 whitespace-nowrap min-w-[150px]">Incentive</th>
                <th class="text-right px-4 py-3.5 whitespace-nowrap min-w-[140px]">Total Paid</th>
                <th class="text-right px-4 py-3.5 whitespace-nowrap min-w-[140px]">Balance Due</th>
                <th class="text-center px-4 py-3.5 whitespace-nowrap min-w-[200px]">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800/80">
              <template x-for="emp in filteredEmployees" :key="emp.id">
                <tr @click="empInfoModalId=emp.id; showEmpInfoModal=true"
                  class="hover:bg-slate-50/70 dark:hover:bg-slate-800/50 transition-colors cursor-pointer"
                  :class="selectedEmps.includes(emp.id) ? 'bg-brand-50/80 dark:bg-brand-950/40' : ''">
                  
                  <!-- Checkbox -->
                  <td class="px-3 py-3.5 text-center whitespace-nowrap" @click.stop>
                    <input type="checkbox" class="rounded cursor-pointer" :checked="selectedEmps.includes(emp.id)"
                      @change="toggleEmpSelect(emp.id, $event.target.checked)" />
                  </td>

                  <!-- EMP ID -->
                  <td class="px-4 py-3.5 whitespace-nowrap">
                    <span class="font-mono text-xs font-bold text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-950 px-2.5 py-1 rounded-md border border-brand-200/60 dark:border-brand-800/60 whitespace-nowrap inline-block"
                      x-text="emp.empId"></span>
                  </td>

                  <!-- Name -->
                  <td class="px-4 py-3.5 whitespace-nowrap">
                    <div class="font-bold text-slate-900 dark:text-white text-sm sm:text-[15px] leading-tight" x-text="emp.name"></div>
                    <div class="text-xs text-slate-400 mt-0.5" x-text="emp.email || ''"></div>
                  </td>

                  <!-- Mobile -->
                  <td class="px-4 py-3.5 text-sm font-mono text-slate-600 dark:text-slate-400 whitespace-nowrap font-medium" x-text="emp.mobile"></td>

                  <!-- Designation / Dept -->
                  <td class="px-4 py-3.5 whitespace-nowrap">
                    <div class="text-sm font-semibold text-slate-800 dark:text-slate-200 leading-tight" x-text="emp.designation || '—'"></div>
                    <div class="text-xs text-slate-400 mt-0.5" x-text="emp.department || ''"></div>
                  </td>
                  
                  <!-- Sales -->
                  <td class="px-4 py-3.5 text-center whitespace-nowrap">
                    <template x-if="isEmpSalesRole(emp)">
                      <span class="text-sm font-bold font-mono text-slate-800 dark:text-slate-200 px-3 py-1 rounded-md bg-slate-100 dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700 whitespace-nowrap inline-block"
                        x-text="empTotalSales(emp) + ' Deals'"></span>
                    </template>
                    <template x-if="!isEmpSalesRole(emp)">
                      <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200/80 dark:border-slate-700 whitespace-nowrap">Fixed Staff</span>
                    </template>
                  </td>

                  <!-- Incentive -->
                  <td class="px-4 py-3.5 text-right whitespace-nowrap">
                    <template x-if="isEmpSalesRole(emp)">
                      <span class="text-sm sm:text-[15px] font-bold text-brand-600 dark:text-brand-400 font-mono leading-tight whitespace-nowrap inline-block"
                        x-text="fmtCurrency(empTotalCommission(emp))"></span>
                    </template>
                    <template x-if="!isEmpSalesRole(emp)">
                      <span class="text-xs sm:text-sm text-slate-600 dark:text-slate-400 font-mono font-semibold whitespace-nowrap inline-block"
                        x-text="fmtCurrency(parseInt(emp.basicSalary) || 10000) + ' /mo'"></span>
                    </template>
                  </td>

                  <!-- Total Paid -->
                  <td class="px-4 py-3.5 text-right whitespace-nowrap">
                    <span class="text-sm sm:text-[15px] font-bold font-mono text-emerald-600 dark:text-emerald-400 leading-tight whitespace-nowrap inline-block"
                      x-text="fmtCurrency(empTotalPaid(emp))"></span>
                  </td>

                  <!-- Balance Due -->
                  <td class="px-4 py-3.5 text-right whitespace-nowrap">
                    <span class="text-sm sm:text-[15px] font-bold font-mono leading-tight whitespace-nowrap inline-block" :class="empBalance(emp)>0 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-400 font-medium'"
                      x-text="fmtCurrency(empBalance(emp))"></span>
                  </td>

                  <!-- Actions -->
                  <td class="px-4 py-3.5 whitespace-nowrap">
                    <div class="flex items-center justify-center gap-1.5" @click.stop>
                      <button @click="openDirectSalaryPaymentModal(emp)"
                        class="p-1.5 rounded-lg text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950 transition-colors cursor-pointer"
                        title="Direct UPI Salary / Commission Payment">
                        <i class="fa-solid fa-bolt text-xs"></i>
                      </button>
                      <button x-show="['sales', 'sales_member', 'sales_leader'].includes((emp.role || '').toLowerCase()) || (emp.department || '').toLowerCase().includes('sales')"
                        @click="openSalesSalaryModal ? openSalesSalaryModal(emp) : openDirectSalaryPaymentModal(emp)"
                        class="p-1.5 rounded-lg text-teal-600 hover:bg-teal-50 dark:hover:bg-teal-950 transition-colors cursor-pointer"
                        title="Sales Salary & Quota Breakdown">
                        <i class="fa-solid fa-calculator text-xs"></i>
                      </button>
                      <button @click="openEmpDetail(emp.id)"
                        class="p-1.5 rounded-lg text-brand-600 hover:bg-brand-50 dark:hover:bg-brand-950 transition-colors cursor-pointer"
                        title="View Sales & Payments">
                        <i class="fa-solid fa-eye text-xs"></i>
                      </button>
                      <button @click="empCardId=emp.id; showEmpCardModal=true"
                        class="p-1.5 rounded-lg text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950 transition-colors cursor-pointer"
                        title="Employee Card">
                        <i class="fa-solid fa-id-card text-xs"></i>
                      </button>
                      <button @click="openEmpSaleModal(emp.id)"
                        class="p-1.5 rounded-lg text-green-600 hover:bg-green-50 dark:hover:bg-green-950 transition-colors cursor-pointer"
                        title="Record Sale">
                        <i class="fa-solid fa-circle-plus text-xs"></i>
                      </button>
                      <button @click="openEmpPayModal(emp.id)"
                        class="p-1.5 rounded-lg text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950 transition-colors cursor-pointer"
                        title="Pay Incentive">
                        <i class="fa-solid fa-indian-rupee-sign text-xs"></i>
                      </button>
                      <button @click="editEmployee(emp.id)"
                        class="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                        title="Edit">
                        <i class="fa-solid fa-pencil text-xs"></i>
                      </button>
                      <button @click="deleteEmployee(emp.id)"
                        class="p-1.5 rounded-lg text-red-400 hover:bg-red-50 dark:hover:bg-red-950 transition-colors cursor-pointer"
                        title="Delete">
                        <i class="fa-solid fa-trash text-xs"></i>
                      </button>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
            <tfoot x-show="employees.length>1"
              class="bg-slate-50/90 dark:bg-slate-800/90 font-bold text-xs sm:text-[13px] border-t-2 border-slate-200 dark:border-slate-700">
              <tr>
                <td class="px-3 py-3.5"></td>
                <td class="px-4 py-3.5 text-slate-600 dark:text-slate-300" colspan="4">
                  <span>Total (<span x-text="employees.length"></span> Staff Members)</span>
                </td>
                <td class="px-4 py-3.5 text-center text-slate-800 dark:text-slate-200 font-mono whitespace-nowrap"
                  x-text="employees.reduce((s,e)=>s+empTotalSales(e),0) + ' Deals'"></td>
                <td class="px-4 py-3.5 text-right text-brand-600 dark:text-brand-400 font-mono text-sm sm:text-[15px] whitespace-nowrap"
                  x-text="fmtCurrency(employees.reduce((s,e)=>s+empTotalCommission(e),0))"></td>
                <td class="px-4 py-3.5 text-right text-emerald-600 dark:text-emerald-400 font-mono text-sm sm:text-[15px] whitespace-nowrap"
                  x-text="fmtCurrency(employees.reduce((s,e)=>s+empTotalPaid(e),0))"></td>
                <td class="px-4 py-3.5 text-right text-red-500 font-mono text-sm sm:text-[15px] whitespace-nowrap"
                  x-text="fmtCurrency(employees.reduce((s,e)=>s+empBalance(e),0))"></td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>'''

with open('AdminPanel.html', 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '<!-- Employees Table Container -->'
end_marker = '<!-- ══ PAYROLL ══ -->'

s_idx = content.find(start_marker)
if s_idx == -1:
    print("Error: start_marker not found!")
    sys.exit(1)

e_idx = content.find(end_marker, s_idx)
if e_idx == -1:
    print("Error: end_marker not found!")
    sys.exit(1)

# Find closing </main> right before end_marker
main_close = content.rfind('</main>', s_idx, e_idx)

new_content = content[:s_idx] + new_table_html + "\n      </div>\n    " + content[main_close:]

with open('AdminPanel.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Updated AdminPanel.html successfully!")

# Sync to index.html and InvoicePro Admin\AdminPanel.html
shutil.copyfile('AdminPanel.html', 'index.html')
sub_path = os.path.join('InvoicePro Admin', 'AdminPanel.html')
if os.path.exists(os.path.dirname(sub_path)):
    shutil.copyfile('AdminPanel.html', sub_path)

print("Synced all copies successfully!")

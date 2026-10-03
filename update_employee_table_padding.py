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
          <table x-show="employees.length>0" class="w-full text-sm border-collapse min-w-[1100px]">
            <thead class="bg-slate-50/90 dark:bg-slate-800/90 text-xs sm:text-[13px] font-bold text-slate-700 dark:text-slate-200 uppercase tracking-wider border-b border-slate-200 dark:border-slate-700 select-none">
              <tr>
                <th class="px-4 py-3.5 w-10 text-center">
                  <input type="checkbox" class="rounded cursor-pointer"
                    :checked="selectedEmps.length === filteredEmployees.length && filteredEmployees.length > 0"
                    :indeterminate="selectedEmps.length > 0 && selectedEmps.length < filteredEmployees.length"
                    @change="toggleSelectAllEmps($event.target.checked)" />
                </th>
                <th class="text-left px-4 py-3.5 whitespace-nowrap">EMP ID</th>
                <th class="text-left px-4 py-3.5 whitespace-nowrap">Name</th>
                <th class="text-left px-4 py-3.5 whitespace-nowrap">Mobile</th>
                <th class="text-left px-4 py-3.5 whitespace-nowrap">Designation / Dept</th>
                <th class="text-center px-4 py-3.5 whitespace-nowrap">Sales</th>
                <th class="text-right px-4 py-3.5 whitespace-nowrap">Incentive</th>
                <th class="text-right px-4 py-3.5 whitespace-nowrap">Total Paid</th>
                <th class="text-right px-4 py-3.5 whitespace-nowrap">Balance Due</th>
                <th class="text-center px-4 py-3.5 whitespace-nowrap">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 dark:divide-slate-800/80">
              <template x-for="emp in filteredEmployees" :key="emp.id">
                <tr @click="empInfoModalId=emp.id; showEmpInfoModal=true"
                  class="hover:bg-slate-50/70 dark:hover:bg-slate-800/50 transition-colors cursor-pointer"
                  :class="selectedEmps.includes(emp.id) ? 'bg-brand-50/80 dark:bg-brand-950/40' : ''">
                  <td class="px-4 py-3.5 text-center" @click.stop>
                    <input type="checkbox" class="rounded cursor-pointer" :checked="selectedEmps.includes(emp.id)"
                      @change="toggleEmpSelect(emp.id, $event.target.checked)" />
                  </td>
                  <td class="px-4 py-3.5 whitespace-nowrap">
                    <span class="font-mono text-xs font-bold text-brand-600 dark:text-brand-400 bg-brand-50 dark:bg-brand-950 px-2.5 py-1 rounded-md border border-brand-200/60 dark:border-brand-800/60 whitespace-nowrap"
                      x-text="emp.empId"></span>
                  </td>
                  <td class="px-4 py-3.5">
                    <div class="font-bold text-slate-900 dark:text-white text-sm sm:text-[15px] leading-tight" x-text="emp.name"></div>
                    <div class="text-xs text-slate-400 mt-0.5" x-text="emp.email || ''"></div>
                  </td>
                  <td class="px-4 py-3.5 text-sm font-mono text-slate-600 dark:text-slate-400 whitespace-nowrap font-medium" x-text="emp.mobile"></td>
                  <td class="px-4 py-3.5">
                    <div class="text-sm font-semibold text-slate-800 dark:text-slate-200 leading-tight" x-text="emp.designation || '—'"></div>
                    <div class="text-xs text-slate-400 mt-0.5" x-text="emp.department || ''"></div>
                  </td>
                  
                  <td class="px-4 py-3.5 text-center">
                    <template x-if="isEmpSalesRole(emp)">
                      <span class="text-sm font-bold font-mono text-slate-800 dark:text-slate-200 px-2.5 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700"
                        x-text="empTotalSales(emp) + ' Deals'"></span>
                    </template>
                    <template x-if="!isEmpSalesRole(emp)">
                      <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200/80 dark:border-slate-700">Fixed Staff</span>
                    </template>
                  </td>
                  <td class="px-4 py-3.5 text-right">
                    <template x-if="isEmpSalesRole(emp)">
                      <span class="text-sm sm:text-[15px] font-bold text-brand-600 dark:text-brand-400 font-mono leading-tight"
                        x-text="fmtCurrency(empTotalCommission(emp))"></span>
                    </template>
                    <template x-if="!isEmpSalesRole(emp)">
                      <span class="text-xs sm:text-sm text-slate-600 dark:text-slate-400 font-mono font-semibold"
                        x-text="fmtCurrency(parseInt(emp.basicSalary) || 10000) + ' /mo'"></span>
                    </template>
                  </td>
                  <td class="px-4 py-3.5 text-right">
                    <span class="text-sm sm:text-[15px] font-bold font-mono text-emerald-600 dark:text-emerald-400 leading-tight"
                      x-text="fmtCurrency(empTotalPaid(emp))"></span>
                  </td>
                  <td class="px-4 py-3.5 text-right">
                    <span class="text-sm sm:text-[15px] font-bold font-mono leading-tight" :class="empBalance(emp)>0 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-400 font-medium'"
                      x-text="fmtCurrency(empBalance(emp))"></span>
                  </td>
                  <td class="px-4 py-3.5">
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
                <td class="px-4 py-3.5"></td>
                <td class="px-4 py-3.5 text-slate-600 dark:text-slate-300" colspan="4">
                  <span>Total (<span x-text="employees.length"></span> Staff Members)</span>
                </td>
                <td class="px-4 py-3.5 text-center text-slate-800 dark:text-slate-200 font-mono"
                  x-text="employees.reduce((s,e)=>s+empTotalSales(e),0) + ' Deals'"></td>
                <td class="px-4 py-3.5 text-right text-brand-600 dark:text-brand-400 font-mono text-sm sm:text-[15px]"
                  x-text="fmtCurrency(employees.reduce((s,e)=>s+empTotalCommission(e),0))"></td>
                <td class="px-4 py-3.5 text-right text-emerald-600 dark:text-emerald-400 font-mono text-sm sm:text-[15px]"
                  x-text="fmtCurrency(employees.reduce((s,e)=>s+empTotalPaid(e),0))"></td>
                <td class="px-4 py-3.5 text-right text-red-500 font-mono text-sm sm:text-[15px]"
                  x-text="fmtCurrency(employees.reduce((s,e)=>s+empBalance(e),0))"></td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>'''

with open('AdminPanel.html', 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = '<div class="bg-white dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800 overflow-hidden overflow-x-auto">\n          <div x-show="employees.length===0"'
if start_marker not in content:
    # Try more flexible match
    start_tag = '<table x-show="employees.length>0" class="w-full text-sm min-w-[1060px]">'
    s_idx = content.find(start_tag)
    if s_idx == -1:
        print("Error: table tag not found!")
        sys.exit(1)
    # find preceding <div
    div_start = content.rfind('<div', 0, s_idx)
    # find closing </div> after </table>
    table_end = content.find('</table>', s_idx)
    div_end = content.find('</div>', table_end) + len('</div>')
    new_content = content[:div_start] + new_table_html + content[div_end:]
else:
    end_marker = '</table>\n        </div>'
    s_idx = content.find(start_marker)
    e_idx = content.find(end_marker, s_idx) + len(end_marker)
    new_content = content[:s_idx] + new_table_html + content[e_idx:]

with open('AdminPanel.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Updated AdminPanel.html successfully!")

# Sync to index.html and InvoicePro Admin\AdminPanel.html
shutil.copyfile('AdminPanel.html', 'index.html')
sub_path = os.path.join('InvoicePro Admin', 'AdminPanel.html')
if os.path.exists(os.path.dirname(sub_path)):
    shutil.copyfile('AdminPanel.html', sub_path)

print("Synced all copies successfully!")

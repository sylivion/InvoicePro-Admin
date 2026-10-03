# -*- coding: utf-8 -*-
import sys
import os
import shutil

sys.stdout.reconfigure(encoding='utf-8')

new_payroll_html = '''    <main class="flex-1 overflow-y-auto p-6" x-show="view==='payroll' && canAccess('payroll')" x-cloak>
      <div>
        <!-- Header -->
        <div class="flex items-center justify-between mb-5 flex-wrap gap-3">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-purple-50 dark:bg-purple-950/70 border border-purple-200/70 dark:border-purple-800/60 text-purple-600 dark:text-purple-400 flex items-center justify-center text-lg shadow-xs flex-shrink-0">
              <i class="fa-solid fa-money-check-dollar"></i>
            </div>
            <div>
              <h1 class="text-xl font-bold text-slate-900 dark:text-white tracking-tight">Payroll &amp; Salary Disbursement</h1>
              <p class="text-xs text-slate-500 dark:text-slate-400">Manage pending salary disbursements, run payroll payouts, and review past payment history</p>
            </div>
          </div>
          <div class="flex items-center gap-2 flex-wrap">
            <div class="flex items-center gap-1.5 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 px-3 py-1.5 rounded-xl shadow-xs">
              <label class="text-xs font-bold text-gray-500"><i class="fa-solid fa-calendar mr-1 text-purple-500"></i> Cycle:</label>
              <input type="month" x-model="payrollMonth"
                class="text-xs font-mono font-bold bg-transparent text-gray-800 dark:text-gray-200 focus:outline-none" />
              <button x-show="payrollMonth" @click="payrollMonth=''" class="text-slate-400 hover:text-slate-600 text-xs px-1 cursor-pointer" title="Clear / View All Time">✕</button>
            </div>
            <button @click="payrollMonth=''"
              :class="!payrollMonth ? 'bg-purple-600 text-white shadow-xs' : 'border border-gray-200 dark:border-gray-700 text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-950/50'"
              class="px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors cursor-pointer">
              All Time
            </button>
            <button @click="payrollMonth=new Date().toISOString().slice(0,7)"
              :class="payrollMonth === new Date().toISOString().slice(0,7) ? 'bg-purple-600 text-white shadow-xs' : 'border border-gray-200 dark:border-gray-700 text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-950/50'"
              class="px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors cursor-pointer">
              This Month
            </button>
          </div>
        </div>

        <!-- ══ TWO CATEGORY SELECTOR TABS ══ -->
        <div class="flex items-center justify-between gap-3 mb-5 border-b border-slate-200 dark:border-slate-800 pb-3 flex-wrap">
          <div class="inline-flex items-center gap-1.5 bg-slate-100 dark:bg-slate-800/90 p-1 rounded-xl border border-slate-200/80 dark:border-slate-700 shadow-xs">
            <!-- Run Payroll Tab (Pending Payments) -->
            <button @click="payrollTab='run'"
              :class="payrollTab==='run' ? 'bg-white dark:bg-slate-900 text-brand-600 dark:text-brand-400 shadow-xs font-bold border border-slate-200/60 dark:border-slate-700' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 font-medium'"
              class="px-4 py-2 rounded-lg text-xs sm:text-sm transition-all flex items-center gap-2 cursor-pointer">
              <i class="fa-solid fa-bolt-lightning text-xs" :class="payrollTab==='run' ? 'text-amber-500' : 'text-slate-400'"></i>
              <span>Run Payroll</span>
              <span class="px-2 py-0.5 rounded-full text-[11px] font-bold"
                :class="employees.filter(e => getEmpPayrollBalance(e, payrollMonth) > 0).length > 0 ? (payrollTab==='run' ? 'bg-amber-100 dark:bg-amber-950/80 text-amber-700 dark:text-amber-300' : 'bg-amber-50 dark:bg-amber-950/40 text-amber-600') : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300'"
                x-text="employees.filter(e => getEmpPayrollBalance(e, payrollMonth) > 0).length + ' Pending'"></span>
            </button>

            <!-- Salary History Tab (Paid Salaries) -->
            <button @click="payrollTab='history'"
              :class="payrollTab==='history' ? 'bg-white dark:bg-slate-900 text-emerald-600 dark:text-emerald-400 shadow-xs font-bold border border-slate-200/60 dark:border-slate-700' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 font-medium'"
              class="px-4 py-2 rounded-lg text-xs sm:text-sm transition-all flex items-center gap-2 cursor-pointer">
              <i class="fa-solid fa-clock-rotate-left text-xs" :class="payrollTab==='history' ? 'text-emerald-500' : 'text-slate-400'"></i>
              <span>Salary History</span>
              <span class="px-2 py-0.5 rounded-full text-[11px] font-bold"
                :class="payrollTab==='history' ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-700 dark:text-emerald-300' : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300'"
                x-text="employees.filter(e => empTotalPaid(e) > 0).length + ' Paid'"></span>
            </button>
          </div>

          <!-- Quick Context / Help Badge -->
          <div class="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2">
            <template x-if="payrollTab==='run'">
              <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                <i class="fa-solid fa-circle-exclamation text-xs"></i>
                <span>Showing <strong>only unpaid balances</strong> ready for disbursement</span>
              </span>
            </template>
            <template x-if="payrollTab==='history'">
              <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                <i class="fa-solid fa-circle-check text-xs"></i>
                <span>Showing <strong>settled salaries &amp; disbursement logs</strong></span>
              </span>
            </template>
          </div>
        </div>

        <!-- No employees at all in system -->
        <div x-show="employees.length===0"
          class="text-center py-12 bg-white dark:bg-gray-900 rounded-2xl border border-gray-100 dark:border-gray-800 shadow-sm">
          <i class="fa-solid fa-money-check-dollar text-3xl mb-2 block text-gray-300 dark:text-gray-700"></i>
          <p class="text-sm text-gray-400">No employees yet. <button @click="navigate('employees')"
              class="text-brand-600 hover:underline font-bold">Add employees →</button></p>
        </div>

        <!-- ══════════════════════════════════════════════════════════ -->
        <!-- CATEGORY 1: RUN PAYROLL (PENDING PAYMENTS ONLY)           -->
        <!-- ══════════════════════════════════════════════════════════ -->
        <div x-show="payrollTab==='run' && employees.length > 0">
          
          <!-- Run Payroll Summary KPI Cards -->
          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-5">
            <!-- Total Balance Due (Pending Payout) -->
            <div class="rounded-2xl p-4 border shadow-xs"
              :class="employees.reduce((s,e)=>s+getEmpPayrollBalance(e,payrollMonth),0) > 0 ? 'bg-red-50/80 dark:bg-red-950/40 border-red-200 dark:border-red-900' : 'bg-emerald-50/70 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-900'">
              <div class="flex items-center justify-between text-gray-400 mb-1">
                <span class="text-[10px] font-bold uppercase tracking-wider">Pending Payout Due</span>
                <i class="fa-solid fa-hand-holding-dollar text-xs" :class="employees.reduce((s,e)=>s+getEmpPayrollBalance(e,payrollMonth),0) > 0 ? 'text-red-500' : 'text-emerald-500'"></i>
              </div>
              <div class="text-2xl font-bold font-mono" :class="employees.reduce((s,e)=>s+getEmpPayrollBalance(e,payrollMonth),0) > 0 ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400'"
                x-text="fmtCurrency(employees.reduce((s,e)=>s+getEmpPayrollBalance(e,payrollMonth),0))"></div>
              <div class="text-[11px] font-semibold mt-0.5" :class="employees.reduce((s,e)=>s+getEmpPayrollBalance(e,payrollMonth),0) > 0 ? 'text-red-500' : 'text-emerald-600'"
                x-text="employees.filter(e => getEmpPayrollBalance(e, payrollMonth) > 0).length + ' employees pending'"></div>
            </div>

            <!-- Total Deals Made -->
            <div class="bg-white dark:bg-gray-900 rounded-2xl p-4 border border-gray-100 dark:border-gray-800 shadow-xs">
              <div class="flex items-center justify-between text-gray-400 mb-1">
                <span class="text-[10px] font-bold uppercase tracking-wider">Deals Completed</span>
                <i class="fa-solid fa-receipt text-xs text-brand-500"></i>
              </div>
              <div class="text-2xl font-semibold text-brand-600 dark:text-brand-400 font-mono"
                x-text="employees.reduce((s,e)=>s+payrollSalesIn(e,payrollMonth),0)"></div>
              <div class="text-[11px] text-gray-400 mt-0.5" x-text="payrollMonth ? 'Sales in ' + payrollMonth : 'Total Recorded Sales'"></div>
            </div>

            <!-- Net Base Salary -->
            <div class="bg-white dark:bg-gray-900 rounded-2xl p-4 border border-gray-100 dark:border-gray-800 shadow-xs">
              <div class="flex items-center justify-between text-gray-400 mb-1">
                <span class="text-[10px] font-bold uppercase tracking-wider">Net Base Salary</span>
                <i class="fa-solid fa-calculator text-xs text-teal-500"></i>
              </div>
              <div class="text-2xl font-semibold text-teal-600 dark:text-teal-400 font-mono"
                x-text="fmtCurrency(employees.reduce((s,e)=>s+getEmpNetSalary(e,payrollMonth),0))"></div>
              <div class="text-[11px] text-gray-400 mt-0.5">₹15k Base (Deductions Applied)</div>
            </div>

            <!-- Qualified Incentives -->
            <div class="bg-white dark:bg-gray-900 rounded-2xl p-4 border border-gray-100 dark:border-gray-800 shadow-xs">
              <div class="flex items-center justify-between text-gray-400 mb-1">
                <span class="text-[10px] font-bold uppercase tracking-wider">Total Incentive</span>
                <i class="fa-solid fa-gift text-xs text-purple-500"></i>
              </div>
              <div class="text-2xl font-semibold text-purple-600 dark:text-purple-400 font-mono"
                x-text="fmtCurrency(employees.reduce((s,e)=>s+payrollCommIn(e,payrollMonth),0))"></div>
              <div class="text-[11px] text-gray-400 mt-0.5">Post-Target Unlocked Deals</div>
            </div>

            <!-- Total Gross Payable -->
            <div class="bg-white dark:bg-gray-900 rounded-2xl p-4 border border-gray-100 dark:border-gray-800 shadow-xs">
              <div class="flex items-center justify-between text-gray-400 mb-1">
                <span class="text-[10px] font-bold uppercase tracking-wider">Total Payable</span>
                <i class="fa-solid fa-money-bills text-xs text-indigo-500"></i>
              </div>
              <div class="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 font-mono"
                x-text="fmtCurrency(employees.reduce((s,e)=>s+getEmpGrossPay(e,payrollMonth),0))"></div>
              <div class="text-[11px] text-gray-400 mt-0.5">Salary + Incentive Obligation</div>
            </div>
          </div>

          <!-- Pending Disbursements Table (Only Employees with Balance Due > 0) -->
          <div x-show="employees.filter(e => getEmpPayrollBalance(e, payrollMonth) > 0).length > 0"
            class="my-5 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xs overflow-hidden overflow-x-auto">
            <div class="px-4 py-3 bg-amber-50/60 dark:bg-amber-950/30 border-b border-amber-100 dark:border-amber-900/50 flex items-center justify-between flex-wrap gap-2">
              <div class="flex items-center gap-2">
                <i class="fa-solid fa-bolt text-amber-600 text-xs"></i>
                <span class="text-xs sm:text-[13px] font-bold text-amber-900 dark:text-amber-200">Pending Salary Disbursements Queue</span>
                <span class="text-xs text-amber-700/80 dark:text-amber-300/80 font-medium">Click "Pay" to disburse via UPI/QR code or manual entry</span>
              </div>
              <div class="text-xs font-mono font-bold text-amber-800 dark:text-amber-300"
                x-text="'Total Due: ₹' + employees.reduce((s,e)=>s+getEmpPayrollBalance(e,payrollMonth),0).toLocaleString('en-IN')"></div>
            </div>

            <table class="w-full text-sm border-collapse">
              <thead class="bg-slate-50/90 dark:bg-slate-800/90 text-xs sm:text-[13px] font-bold text-slate-700 dark:text-slate-200 uppercase tracking-wider border-b border-slate-200 dark:border-slate-700 select-none">
                <tr>
                  <th class="text-left px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Employee</th>
                  <th class="text-left px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Sales (Breakdown)</th>
                  <th class="text-right px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Net Base Salary</th>
                  <th class="text-right px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Incentive</th>
                  <th class="text-right px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Total Payable</th>
                  <th class="text-right px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Total Paid</th>
                  <th class="text-right px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Balance Due</th>
                  <th class="text-center px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100 dark:divide-slate-800/80">
                <template x-for="emp in employees.filter(e => getEmpPayrollBalance(e, payrollMonth) > 0)" :key="emp.id">
                  <tr @click="empInfoModalId=emp.id; showEmpInfoModal=true"
                    class="hover:bg-slate-50/70 dark:hover:bg-slate-800/50 transition-colors cursor-pointer">
                    
                    <!-- Employee Info -->
                    <td class="px-3 sm:px-4 py-3 sm:py-3.5">
                      <div class="font-bold text-slate-900 dark:text-white text-sm sm:text-[15px] leading-tight" x-text="emp.name"></div>
                      <div class="text-xs text-brand-600 dark:text-brand-400 font-mono font-bold leading-tight mt-1" x-text="emp.empId"></div>
                      <div class="text-xs text-slate-500 dark:text-slate-400 leading-tight mt-0.5"
                        x-text="[emp.designation, emp.department].filter(Boolean).join(' · ')"></div>
                    </td>

                    <!-- Sales Completed -->
                    <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-left">
                      <template x-if="isEmpSalesRole(emp)">
                        <div>
                          <div class="flex items-center gap-2 flex-wrap">
                            <span class="text-sm font-semibold text-slate-900 dark:text-white font-mono"
                              x-text="payrollSalesIn(emp, payrollMonth) + ' Deals'"></span>
                            <template x-if="getEmpPlanBreakdown(emp, payrollMonth).hasSales">
                              <div class="flex items-center gap-1.5 flex-wrap">
                                <!-- 1Y Badge -->
                                <span x-show="getEmpPlanBreakdown(emp, payrollMonth).count1y > 0"
                                  class="px-2 py-0.5 rounded-md text-[10px] sm:text-[11px] font-bold bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800"
                                  x-text="'1Y: ' + getEmpPlanBreakdown(emp, payrollMonth).count1y"></span>
                                <!-- 3Y Badge -->
                                <span x-show="getEmpPlanBreakdown(emp, payrollMonth).count3y > 0"
                                  class="px-2 py-0.5 rounded-md text-[10px] sm:text-[11px] font-bold bg-purple-50 text-purple-700 dark:bg-purple-950 dark:text-purple-300 border border-purple-200 dark:border-purple-800"
                                  x-text="'3Y: ' + getEmpPlanBreakdown(emp, payrollMonth).count3y"></span>
                                <!-- 5Y Badge -->
                                <span x-show="getEmpPlanBreakdown(emp, payrollMonth).count5y > 0"
                                  class="px-2 py-0.5 rounded-md text-[10px] sm:text-[11px] font-bold bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
                                  x-text="'5Y: ' + getEmpPlanBreakdown(emp, payrollMonth).count5y"></span>
                                <!-- VIP Badge -->
                                <span x-show="getEmpPlanBreakdown(emp, payrollMonth).countVip > 0"
                                  class="px-2 py-0.5 rounded-md text-[10px] sm:text-[11px] font-bold bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300 border border-amber-200 dark:border-amber-800"
                                  x-text="'VIP: ' + getEmpPlanBreakdown(emp, payrollMonth).countVip"></span>
                              </div>
                            </template>
                          </div>
                          <div x-show="!getEmpPlanBreakdown(emp, payrollMonth).hasSales" class="text-xs text-slate-400 mt-1">
                            No deals recorded
                          </div>
                        </div>
                      </template>
                      <template x-if="!isEmpSalesRole(emp)">
                        <div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200/80 dark:border-slate-700">
                          <i class="fa-solid fa-briefcase text-xs text-slate-400"></i>
                          <span>Fixed Staff (<span x-text="emp.department || 'Operations'"></span>)</span>
                        </div>
                      </template>
                    </td>

                    <!-- Net Salary Column -->
                    <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-right">
                      <template x-if="isEmpSalesRole(emp)">
                        <div>
                          <div class="text-sm sm:text-[15px] font-bold text-slate-900 dark:text-white font-mono leading-tight"
                            x-text="fmtCurrency(Math.round(getEmpNetSalary(emp, payrollMonth)))"></div>
                          <template x-if="getSalesSalaryBreakdown(emp, payrollMonth).isTargetSatisfied">
                            <div class="text-xs text-emerald-600 dark:text-emerald-400 font-bold flex items-center justify-end gap-1 mt-1">
                              <i class="fa-solid fa-circle-check text-xs"></i> Met Target
                            </div>
                          </template>
                          <template x-if="!getSalesSalaryBreakdown(emp, payrollMonth).isTargetSatisfied">
                            <div class="text-xs text-indigo-600 dark:text-indigo-400 font-medium flex items-center justify-end gap-1 mt-1 whitespace-nowrap">
                              <i class="fa-solid fa-calculator text-[10px]"></i>
                              <span x-text="getSalesSalaryBreakdown(emp, payrollMonth).totalSales > 0 ? (getSalesSalaryBreakdown(emp, payrollMonth).totalSales + ' deals @ ₹' + Math.round(getSalesSalaryBreakdown(emp, payrollMonth).activeRate || (getSalesSalaryBreakdown(emp, payrollMonth).netBaseSalary / getSalesSalaryBreakdown(emp, payrollMonth).totalSales)).toLocaleString('en-IN') + '/sale') : '0 deals'"></span>
                            </div>
                          </template>
                        </div>
                      </template>
                      <template x-if="!isEmpSalesRole(emp)">
                        <div>
                          <div class="text-sm sm:text-[15px] font-bold text-emerald-600 dark:text-emerald-400 font-mono leading-tight">₹10,000</div>
                          <div class="text-xs text-slate-400 font-medium flex items-center justify-end gap-1 mt-1">
                            <span>Fixed Monthly Pay</span>
                          </div>
                        </div>
                      </template>
                    </td>

                    <!-- Incentive Column -->
                    <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-right">
                      <template x-if="isEmpSalesRole(emp)">
                        <div>
                          <div class="text-sm sm:text-[15px] font-bold font-mono leading-tight"
                            :class="payrollCommIn(emp, payrollMonth) > 0 ? 'text-purple-600 dark:text-purple-400 font-bold' : 'text-slate-400 font-medium'"
                            x-text="fmtCurrency(payrollCommIn(emp, payrollMonth))"></div>
                          <div class="text-xs text-slate-400 leading-tight mt-1 whitespace-nowrap"
                            x-text="payrollCommIn(emp, payrollMonth) > 0 ? 'Post-Target' : 'Target Pending'"></div>
                        </div>
                      </template>
                      <template x-if="!isEmpSalesRole(emp)">
                        <div>
                          <div class="text-sm font-medium text-slate-400 font-mono">₹0</div>
                          <div class="text-xs text-slate-400 mt-1">N/A (Non-Sales)</div>
                        </div>
                      </template>
                    </td>

                    <!-- Total Payable (Gross Pay) -->
                    <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-right">
                      <div class="text-sm sm:text-[15px] font-bold text-brand-600 dark:text-brand-400 font-mono leading-tight"
                        x-text="fmtCurrency(getEmpGrossPay(emp, payrollMonth))"></div>
                      <div class="text-[10px] text-slate-400 mt-1 whitespace-nowrap">Salary + Incentive</div>
                    </td>

                    <!-- Total Paid -->
                    <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-right">
                      <div class="text-sm sm:text-[15px] font-bold text-green-600 dark:text-green-400 font-mono leading-tight"
                        x-text="fmtCurrency(empTotalPaid(emp))"></div>
                    </td>

                    <!-- Balance Due -->
                    <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-right">
                      <div class="text-sm sm:text-[15px] font-mono leading-tight font-bold text-red-500"
                        x-text="fmtCurrency(getEmpPayrollBalance(emp, payrollMonth))"></div>
                      <div class="text-[10px] text-red-400 mt-0.5">Pending Payout</div>
                    </td>

                    <!-- Actions -->
                    <td class="px-3 sm:px-4 py-3 sm:py-3.5">
                      <div class="flex items-center justify-center gap-1.5" @click.stop>
                        <!-- View Salary & Quota Deduction Breakdown -->
                        <button @click="openSalesSalaryModal(emp)"
                          class="p-1.5 rounded-lg text-teal-600 hover:bg-teal-50 dark:hover:bg-teal-950 transition-colors cursor-pointer"
                          title="View Full Salary Deduction Breakdown">
                          <i class="fa-solid fa-calculator text-xs"></i>
                        </button>

                        <!-- Direct UPI / QR Salary Payment -->
                        <button @click="openDirectSalaryPaymentModal(emp, getEmpPayrollBalance(emp, payrollMonth))"
                          class="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-xs transition-all flex items-center gap-1.5 cursor-pointer whitespace-nowrap"
                          :title="'Pay Outstanding Balance: ₹' + getEmpPayrollBalance(emp, payrollMonth).toLocaleString('en-IN')">
                          <i class="fa-solid fa-bolt text-[10px]"></i>
                          <i class="fa-solid fa-qrcode text-xs"></i>
                          <span>Pay</span>
                        </button>

                        <!-- Generate & Print Official Salary Slip -->
                        <button @click="generateSalarySlip(emp, payrollMonth)"
                          class="p-1.5 rounded-lg text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-950 transition-colors cursor-pointer"
                          title="Generate &amp; Print Official Salary Slip">
                          <i class="fa-solid fa-file-invoice text-xs"></i>
                        </button>

                        <!-- Pay record manual -->
                        <button @click="openEmpPayModal(emp.id)"
                          class="p-1.5 rounded-lg text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950 transition-colors cursor-pointer"
                          title="Record Payment Manual">
                          <i class="fa-solid fa-indian-rupee-sign text-xs"></i>
                        </button>

                        <!-- View detail -->
                        <button @click="openEmpDetail(emp.id)"
                          class="p-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-950 transition-colors cursor-pointer"
                          title="View Sales &amp; Payments">
                          <i class="fa-solid fa-eye text-xs"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>

          <!-- Empty State: All Paid / Settled in this cycle -->
          <div x-show="employees.filter(e => getEmpPayrollBalance(e, payrollMonth) > 0).length === 0"
            class="text-center py-12 px-4 bg-emerald-50/50 dark:bg-emerald-950/20 rounded-2xl border border-emerald-200 dark:border-emerald-800/80 my-5 shadow-xs">
            <div class="w-12 h-12 rounded-2xl bg-emerald-100 dark:bg-emerald-900/60 text-emerald-600 dark:text-emerald-300 flex items-center justify-center text-xl mx-auto mb-3 shadow-xs">
              <i class="fa-solid fa-circle-check"></i>
            </div>
            <h3 class="text-base font-bold text-emerald-900 dark:text-emerald-200">All Payroll Settled!</h3>
            <p class="text-xs text-emerald-700/80 dark:text-emerald-400/80 max-w-md mx-auto mt-1">
              There are no pending salary disbursements for <span class="font-bold" x-text="payrollMonth ? payrollMonth : 'this period'"></span>. All employees have received their full compensation.
            </p>
            <div class="mt-4 flex items-center justify-center gap-2">
              <button @click="payrollTab='history'"
                class="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs transition-colors shadow-xs flex items-center gap-1.5 cursor-pointer">
                <i class="fa-solid fa-clock-rotate-left text-xs"></i>
                <span>View Salary History &amp; Slips →</span>
              </button>
            </div>
          </div>

          <!-- Plan Quota Performance Breakdown Cards -->
          <div class="mt-8">
            <div class="flex items-center justify-between mb-4">
              <div class="flex items-center gap-2">
                <div class="w-2.5 h-2.5 rounded-full bg-indigo-500"></div>
                <h3 class="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-wider">Sales Plan Quota &amp; Shortfall Breakdown</h3>
              </div>
              <span class="text-xs text-gray-400">Benchmark target applies to major sold plan</span>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <template x-for="emp in employees" :key="'plan-card-' + emp.id">
                <div class="bg-white dark:bg-gray-900 rounded-2xl p-4 border border-gray-100 dark:border-gray-800 shadow-xs hover:border-brand-200 dark:hover:border-brand-800 transition-colors">
                  <!-- Card Header -->
                  <div class="flex items-center justify-between mb-3 pb-3 border-b border-gray-100 dark:border-gray-800">
                    <div class="flex items-center gap-3">
                      <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-indigo-600 text-white font-semibold flex items-center justify-center text-sm shadow-xs"
                        x-text="(emp.name || 'E').charAt(0).toUpperCase()"></div>
                      <div>
                        <h4 class="font-bold text-sm text-gray-900 dark:text-white" x-text="emp.name"></h4>
                        <div class="flex items-center gap-2 mt-0.5">
                          <span class="text-xs font-mono font-bold text-brand-600 dark:text-brand-400" x-text="emp.empId"></span>
                          <span class="text-xs text-gray-400" x-text="emp.designation || emp.department || 'Sales Executive'"></span>
                        </div>
                      </div>
                    </div>
                    <button @click="openSalesSalaryModal(emp)" class="px-2.5 py-1 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-teal-50 dark:hover:bg-teal-950 text-teal-700 dark:text-teal-300 text-[11px] font-bold transition-all flex items-center gap-1 cursor-pointer">
                      <i class="fa-solid fa-calculator"></i> Full Modal
                    </button>
                  </div>

                  <!-- For Sales Staff: Multi-Plan Target Pills & Shortfall Deduction Engine -->
                  <template x-if="isEmpSalesRole(emp)">
                    <div class="space-y-3">
                      <div class="grid grid-cols-4 gap-2 pt-1 text-center text-xs">
                        <div class="p-2 rounded-xl bg-indigo-50/70 dark:bg-indigo-950/40 border border-indigo-100 dark:border-indigo-900">
                          <div class="text-[10px] font-bold text-indigo-700 dark:text-indigo-300">1 Year</div>
                          <div class="text-base font-semibold text-indigo-900 dark:text-indigo-200 font-mono" x-text="getEmpPlanBreakdown(emp, payrollMonth).count1y"></div>
                          <div class="text-[9px] text-gray-400">Target 15</div>
                        </div>
                        <div class="p-2 rounded-xl bg-purple-50/70 dark:bg-purple-950/40 border border-purple-100 dark:border-purple-900">
                          <div class="text-[10px] font-bold text-purple-700 dark:text-purple-300">3 Year</div>
                          <div class="text-base font-semibold text-purple-900 dark:text-purple-200 font-mono" x-text="getEmpPlanBreakdown(emp, payrollMonth).count3y"></div>
                          <div class="text-[9px] text-gray-400">Target 10</div>
                        </div>
                        <div class="p-2 rounded-xl bg-emerald-50/70 dark:bg-emerald-950/40 border border-emerald-100 dark:border-emerald-900">
                          <div class="text-[10px] font-bold text-emerald-700 dark:text-emerald-300">5 Year</div>
                          <div class="text-base font-semibold text-emerald-900 dark:text-emerald-200 font-mono" x-text="getEmpPlanBreakdown(emp, payrollMonth).count5y"></div>
                          <div class="text-[9px] text-gray-400">Target 7</div>
                        </div>
                        <div class="p-2 rounded-xl bg-amber-50/70 dark:bg-amber-950/40 border border-amber-100 dark:border-amber-900">
                          <div class="text-[10px] font-bold text-amber-700 dark:text-amber-300">VIP Lifetime</div>
                          <div class="text-base font-semibold text-amber-900 dark:text-amber-200 font-mono" x-text="getEmpPlanBreakdown(emp, payrollMonth).countVip"></div>
                          <div class="text-[9px] text-gray-400">Target 3</div>
                        </div>
                      </div>

                      <div class="p-3 rounded-xl border text-xs space-y-1.5"
                        :class="getSalesSalaryBreakdown(emp, payrollMonth).isTargetSatisfied ? 'bg-emerald-50/60 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-200' : 'bg-amber-50/60 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800 text-amber-900 dark:text-amber-200'">
                        <div class="flex items-center justify-between font-bold">
                          <span>
                            <i class="fa-solid" :class="getSalesSalaryBreakdown(emp, payrollMonth).isTargetSatisfied ? 'fa-circle-check text-emerald-600' : 'fa-triangle-exclamation text-amber-600'"></i>
                            <span x-text="getSalesSalaryBreakdown(emp, payrollMonth).isTargetSatisfied ? 'Quota Satisfied (Full ₹15,000 Base Salary)' : 'Benchmark Target: ' + getSalesSalaryBreakdown(emp, payrollMonth).majorPlan.name + ' (' + getSalesSalaryBreakdown(emp, payrollMonth).benchmarkTarget + ' Deals)'"></span>
                          </span>
                          <span class="font-mono text-sm font-semibold" x-text="'Net Salary: ₹' + getEmpNetSalary(emp, payrollMonth).toLocaleString('en-IN')"></span>
                        </div>
                        <div class="flex items-center justify-between text-[11px] text-gray-600 dark:text-gray-400">
                          <span>Total Deals: <strong x-text="getSalesSalaryBreakdown(emp, payrollMonth).totalSales"></strong> · Major Plan Sales: <strong x-text="getSalesSalaryBreakdown(emp, payrollMonth).majorPlan.count"></strong></span>
                          <span x-show="!getSalesSalaryBreakdown(emp, payrollMonth).isTargetSatisfied" class="text-red-500 font-semibold">
                            Shortfall: <span x-text="getSalesSalaryBreakdown(emp, payrollMonth).shortfallSales"></span> deals &rarr; -₹<span x-text="getSalesSalaryBreakdown(emp, payrollMonth).shortfallDeduction.toLocaleString('en-IN')"></span> deduction (@ ₹<span x-text="getSalesSalaryBreakdown(emp, payrollMonth).deductionRatePerSale"></span>/deal)
                          </span>
                        </div>
                      </div>
                    </div>
                  </template>

                  <!-- For Non-Sales Staff: Clean Fixed 10k Salary Banner -->
                  <template x-if="!isEmpSalesRole(emp)">
                    <div class="p-3.5 rounded-xl bg-gray-50 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700 flex items-center justify-between text-xs">
                      <div class="flex items-center gap-2.5">
                        <span class="w-8 h-8 rounded-xl bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 flex items-center justify-center text-xs font-semibold">
                          <i class="fa-solid fa-briefcase"></i>
                        </span>
                        <div>
                          <div class="font-bold text-gray-800 dark:text-gray-200"><span x-text="emp.department || 'Operations'"></span> Department (Fixed Staff)</div>
                          <div class="text-[11px] text-gray-400">Fixed Monthly Salary: ₹10,000 · No sales targets or shortfall deductions applied.</div>
                        </div>
                      </div>
                      <div class="text-right">
                        <div class="text-base font-semibold text-emerald-600 dark:text-emerald-400 font-mono">₹10,000</div>
                        <div class="text-[10px] text-gray-400 font-medium">Monthly Net Pay</div>
                      </div>
                    </div>
                  </template>

                </div>
              </template>
            </div>
          </div>

        </div>

        <!-- ══════════════════════════════════════════════════════════ -->
        <!-- CATEGORY 2: SALARY HISTORY (PAID RECORDS & LEDGER)         -->
        <!-- ══════════════════════════════════════════════════════════ -->
        <div x-show="payrollTab==='history' && employees.length > 0">
          
          <!-- History KPI Cards -->
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
            <!-- Total Disbursed To Date -->
            <div class="bg-white dark:bg-gray-900 rounded-2xl p-4 border border-emerald-100 dark:border-emerald-950/80 shadow-xs">
              <div class="flex items-center justify-between text-gray-400 mb-1">
                <span class="text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-400">Total Disbursed</span>
                <i class="fa-solid fa-circle-check text-xs text-emerald-500"></i>
              </div>
              <div class="text-2xl font-bold text-emerald-600 dark:text-emerald-400 font-mono"
                x-text="fmtCurrency(employees.reduce((s,e)=>s+empTotalPaid(e),0))"></div>
              <div class="text-[11px] text-gray-400 mt-0.5">Paid salary &amp; incentive compensation</div>
            </div>

            <!-- Employees With Paid Records -->
            <div class="bg-white dark:bg-gray-900 rounded-2xl p-4 border border-gray-100 dark:border-gray-800 shadow-xs">
              <div class="flex items-center justify-between text-gray-400 mb-1">
                <span class="text-[10px] font-bold uppercase tracking-wider">Employees Paid</span>
                <i class="fa-solid fa-users text-xs text-brand-500"></i>
              </div>
              <div class="text-2xl font-bold text-brand-600 dark:text-brand-400 font-mono"
                x-text="employees.filter(e => empTotalPaid(e) > 0).length"></div>
              <div class="text-[11px] text-gray-400 mt-0.5" x-text="'Out of ' + employees.length + ' total staff'"></div>
            </div>

            <!-- Total Payment Transactions -->
            <div class="bg-white dark:bg-gray-900 rounded-2xl p-4 border border-gray-100 dark:border-gray-800 shadow-xs">
              <div class="flex items-center justify-between text-gray-400 mb-1">
                <span class="text-[10px] font-bold uppercase tracking-wider">Payment Transactions</span>
                <i class="fa-solid fa-receipt text-xs text-purple-500"></i>
              </div>
              <div class="text-2xl font-bold text-purple-600 dark:text-purple-400 font-mono"
                x-text="getAllPayrollPayments().length"></div>
              <div class="text-[11px] text-gray-400 mt-0.5">Recorded disbursement entries</div>
            </div>

            <!-- Avg Disbursed Per Paid Employee -->
            <div class="bg-white dark:bg-gray-900 rounded-2xl p-4 border border-gray-100 dark:border-gray-800 shadow-xs">
              <div class="flex items-center justify-between text-gray-400 mb-1">
                <span class="text-[10px] font-bold uppercase tracking-wider">Avg Disbursed</span>
                <i class="fa-solid fa-chart-line text-xs text-indigo-500"></i>
              </div>
              <div class="text-2xl font-bold text-indigo-600 dark:text-indigo-400 font-mono"
                x-text="fmtCurrency(employees.filter(e => empTotalPaid(e) > 0).length > 0 ? Math.round(employees.reduce((s,e)=>s+empTotalPaid(e),0) / employees.filter(e => empTotalPaid(e) > 0).length) : 0)"></div>
              <div class="text-[11px] text-gray-400 mt-0.5">Average payout per employee</div>
            </div>
          </div>

          <!-- History Sub-Controls: View Switcher & Search Bar -->
          <div class="flex items-center justify-between gap-3 mb-4 flex-wrap">
            <div class="inline-flex items-center gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-xl border border-slate-200/80 dark:border-slate-700">
              <button @click="payrollHistoryView='summary'"
                :class="payrollHistoryView==='summary' ? 'bg-white dark:bg-slate-900 text-brand-600 dark:text-brand-400 shadow-xs font-bold' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 font-medium'"
                class="px-3 py-1.5 rounded-lg text-xs transition-all flex items-center gap-1.5 cursor-pointer">
                <i class="fa-solid fa-users text-xs"></i>
                <span>Employee Payout Summary</span>
              </button>
              <button @click="payrollHistoryView='ledger'"
                :class="payrollHistoryView==='ledger' ? 'bg-white dark:bg-slate-900 text-brand-600 dark:text-brand-400 shadow-xs font-bold' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 font-medium'"
                class="px-3 py-1.5 rounded-lg text-xs transition-all flex items-center gap-1.5 cursor-pointer">
                <i class="fa-solid fa-list-check text-xs"></i>
                <span>Disbursement Transactions Ledger</span>
              </button>
            </div>

            <!-- Search Input -->
            <div class="relative min-w-[220px]">
              <i class="fa-solid fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs"></i>
              <input type="text" x-model="payrollHistorySearch" placeholder="Search employee, ID, note..."
                class="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-brand-500 shadow-xs" />
              <button x-show="payrollHistorySearch" @click="payrollHistorySearch=''" class="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs">✕</button>
            </div>
          </div>

          <!-- ── SUB-VIEW A: EMPLOYEE PAID SUMMARY ── -->
          <div x-show="payrollHistoryView==='summary'">
            <div x-show="employees.filter(e => empTotalPaid(e) > 0).length > 0"
              class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xs overflow-hidden overflow-x-auto">
              <table class="w-full text-sm border-collapse">
                <thead class="bg-slate-50/90 dark:bg-slate-800/90 text-xs sm:text-[13px] font-bold text-slate-700 dark:text-slate-200 uppercase tracking-wider border-b border-slate-200 dark:border-slate-700 select-none">
                  <tr>
                    <th class="text-left px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Employee</th>
                    <th class="text-left px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Role / Dept</th>
                    <th class="text-right px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Total Payable</th>
                    <th class="text-right px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Total Disbursed (Paid)</th>
                    <th class="text-center px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Settlement Status</th>
                    <th class="text-right px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Balance Due</th>
                    <th class="text-center px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Actions &amp; Slips</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 dark:divide-slate-800/80">
                  <template x-for="emp in employees.filter(e => empTotalPaid(e) > 0).filter(e => !payrollHistorySearch || (e.name && e.name.toLowerCase().includes(payrollHistorySearch.toLowerCase())) || (e.empId && e.empId.toLowerCase().includes(payrollHistorySearch.toLowerCase())) || (e.department && e.department.toLowerCase().includes(payrollHistorySearch.toLowerCase())))" :key="'paid-emp-' + emp.id">
                    <tr @click="empInfoModalId=emp.id; showEmpInfoModal=true"
                      class="hover:bg-slate-50/70 dark:hover:bg-slate-800/50 transition-colors cursor-pointer">
                      
                      <!-- Employee Info -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5">
                        <div class="font-bold text-slate-900 dark:text-white text-sm sm:text-[15px] leading-tight" x-text="emp.name"></div>
                        <div class="text-xs text-brand-600 dark:text-brand-400 font-mono font-bold leading-tight mt-1" x-text="emp.empId"></div>
                      </td>

                      <!-- Role / Department -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-left">
                        <span class="text-xs font-semibold text-slate-700 dark:text-slate-300" x-text="emp.designation || emp.department || 'Staff'"></span>
                        <div class="text-[11px] text-slate-400 mt-0.5" x-text="isEmpSalesRole(emp) ? 'Sales Commission Staff' : 'Fixed Monthly Staff'"></div>
                      </td>

                      <!-- Total Payable -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-right font-mono text-sm sm:text-[15px] font-semibold text-slate-700 dark:text-slate-300"
                        x-text="fmtCurrency(getEmpGrossPay(emp, payrollMonth))"></td>

                      <!-- Total Paid (Disbursed) -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-right">
                        <div class="text-sm sm:text-[15px] font-bold text-emerald-600 dark:text-emerald-400 font-mono leading-tight"
                          x-text="fmtCurrency(empTotalPaid(emp))"></div>
                        <div class="text-[10px] text-slate-400 mt-0.5" x-text="(emp.payments ? emp.payments.length : 0) + ' transactions'"></div>
                      </td>

                      <!-- Settlement Status Badge -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-center">
                        <template x-if="getEmpPayrollBalance(emp, payrollMonth) <= 0">
                          <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                            <i class="fa-solid fa-circle-check text-xs text-emerald-600"></i> Fully Settled
                          </span>
                        </template>
                        <template x-if="getEmpPayrollBalance(emp, payrollMonth) > 0">
                          <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                            <i class="fa-solid fa-clock text-xs text-amber-600"></i> Partially Paid
                          </span>
                        </template>
                      </td>

                      <!-- Balance Due -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-right font-mono text-sm sm:text-[15px]"
                        :class="getEmpPayrollBalance(emp, payrollMonth) > 0 ? 'text-red-500 font-bold' : 'text-slate-400 font-medium'"
                        x-text="fmtCurrency(getEmpPayrollBalance(emp, payrollMonth))"></td>

                      <!-- Actions & Slips -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5">
                        <div class="flex items-center justify-center gap-1.5" @click.stop>
                          <!-- Generate & Print Salary Slip -->
                          <button @click="generateSalarySlip(emp, payrollMonth)"
                            class="px-2.5 py-1 rounded-lg bg-purple-50 hover:bg-purple-100 dark:bg-purple-950/60 dark:hover:bg-purple-900 border border-purple-200 dark:border-purple-800 text-purple-700 dark:text-purple-300 text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer shadow-xs"
                            title="Generate &amp; Print Official Salary Slip">
                            <i class="fa-solid fa-file-invoice text-xs"></i>
                            <span>Salary Slip</span>
                          </button>

                          <!-- View Details & Transactions -->
                          <button @click="openEmpDetail(emp.id)"
                            class="p-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-950 transition-colors cursor-pointer"
                            title="View Full Payment History">
                            <i class="fa-solid fa-eye text-xs"></i>
                          </button>

                          <!-- Calculation Breakdown -->
                          <button @click="openSalesSalaryModal(emp)"
                            class="p-1.5 rounded-lg text-teal-600 hover:bg-teal-50 dark:hover:bg-teal-950 transition-colors cursor-pointer"
                            title="View Calculation Breakdown">
                            <i class="fa-solid fa-calculator text-xs"></i>
                          </button>
                        </div>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>

            <!-- Empty State for Paid Summary -->
            <div x-show="employees.filter(e => empTotalPaid(e) > 0).length === 0"
              class="text-center py-12 px-4 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 my-5 shadow-xs">
              <i class="fa-solid fa-clock-rotate-left text-3xl text-slate-300 dark:text-slate-700 mb-2 block"></i>
              <h4 class="text-sm font-bold text-slate-700 dark:text-slate-300">No Disbursed Salaries Found</h4>
              <p class="text-xs text-slate-400 max-w-sm mx-auto mt-1">
                No salary payments have been recorded yet for the selected cycle. Go to "Run Payroll" to initiate payouts.
              </p>
              <button @click="payrollTab='run'"
                class="mt-4 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-700 text-white font-bold text-xs transition-colors shadow-xs inline-flex items-center gap-1.5 cursor-pointer">
                <i class="fa-solid fa-bolt text-xs"></i>
                <span>Go to Run Payroll →</span>
              </button>
            </div>
          </div>

          <!-- ── SUB-VIEW B: TRANSACTIONS LEDGER ── -->
          <div x-show="payrollHistoryView==='ledger'">
            <div x-show="getAllPayrollPayments().length > 0"
              class="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/80 dark:border-slate-800 shadow-xs overflow-hidden overflow-x-auto">
              <table class="w-full text-sm border-collapse">
                <thead class="bg-slate-50/90 dark:bg-slate-800/90 text-xs sm:text-[13px] font-bold text-slate-700 dark:text-slate-200 uppercase tracking-wider border-b border-slate-200 dark:border-slate-700 select-none">
                  <tr>
                    <th class="text-left px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Payment Date &amp; Time</th>
                    <th class="text-left px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Employee</th>
                    <th class="text-left px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Payment Mode</th>
                    <th class="text-left px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Reference / Note</th>
                    <th class="text-right px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Amount Disbursed</th>
                    <th class="text-center px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">Actions</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 dark:divide-slate-800/80">
                  <template x-for="(p, idx) in getAllPayrollPayments().filter(p => !payrollHistorySearch || (p.empName && p.empName.toLowerCase().includes(payrollHistorySearch.toLowerCase())) || (p.empId && p.empId.toLowerCase().includes(payrollHistorySearch.toLowerCase())) || (p.note && p.note.toLowerCase().includes(payrollHistorySearch.toLowerCase())) || (p.method && p.method.toLowerCase().includes(payrollHistorySearch.toLowerCase())))" :key="'pay-tx-' + idx">
                    <tr class="hover:bg-slate-50/70 dark:hover:bg-slate-800/50 transition-colors">
                      <!-- Date -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">
                        <div class="font-mono text-xs sm:text-[13px] font-bold text-slate-800 dark:text-slate-200" x-text="p.date ? p.date.slice(0, 10) : (p.createdAt ? p.createdAt.slice(0, 10) : '—')"></div>
                        <div class="text-[10px] text-slate-400 mt-0.5" x-text="p.date && p.date.length > 10 ? p.date.slice(11, 16) : (p.createdAt && p.createdAt.length > 10 ? p.createdAt.slice(11, 16) : '')"></div>
                      </td>

                      <!-- Employee -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5">
                        <div class="font-bold text-slate-900 dark:text-white text-sm sm:text-[14px]" x-text="p.empName"></div>
                        <div class="text-xs text-brand-600 dark:text-brand-400 font-mono font-bold mt-0.5" x-text="p.empId"></div>
                      </td>

                      <!-- Mode -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5 whitespace-nowrap">
                        <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                          <i class="fa-solid" :class="p.method==='upi'||p.method==='qr' ? 'fa-qrcode text-emerald-500' : (p.method==='bank' ? 'fa-building-columns text-blue-500' : (p.method==='cash' ? 'fa-money-bill-wave text-amber-500' : 'fa-credit-card text-purple-500'))"></i>
                          <span x-text="(p.method || 'Direct Transfer').toUpperCase()"></span>
                        </span>
                      </td>

                      <!-- Reference / Note -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-xs text-slate-600 dark:text-slate-400 max-w-xs truncate"
                        x-text="p.note || p.reference || 'Salary Disbursement'"></td>

                      <!-- Amount -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-right font-mono text-sm sm:text-[15px] font-bold text-emerald-600 dark:text-emerald-400"
                        x-text="fmtCurrency(p.amount || 0)"></td>

                      <!-- Actions -->
                      <td class="px-3 sm:px-4 py-3 sm:py-3.5 text-center">
                        <div class="flex items-center justify-center gap-1.5">
                          <button @click="generateSalarySlip(p.emp, payrollMonth)"
                            class="p-1.5 rounded-lg text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-950 transition-colors cursor-pointer"
                            title="Print Salary Slip">
                            <i class="fa-solid fa-file-invoice text-xs"></i>
                          </button>
                          <button @click="openEmpDetail(p.emp.id)"
                            class="p-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-950 transition-colors cursor-pointer"
                            title="View Employee Detail">
                            <i class="fa-solid fa-eye text-xs"></i>
                          </button>
                        </div>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>

            <!-- Empty State for Transactions Ledger -->
            <div x-show="getAllPayrollPayments().length === 0"
              class="text-center py-12 px-4 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 my-5 shadow-xs">
              <i class="fa-solid fa-receipt text-3xl text-slate-300 dark:text-slate-700 mb-2 block"></i>
              <h4 class="text-sm font-bold text-slate-700 dark:text-slate-300">No Transactions Recorded</h4>
              <p class="text-xs text-slate-400 max-w-sm mx-auto mt-1">
                No individual payment transactions exist for the selected cycle.
              </p>
            </div>
          </div>

        </div>

      </div>
    </main>'''

def apply_update(filepath):
    print(f"Reading {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    start_tag = '<main class="flex-1 overflow-y-auto p-6" x-show="view===\'payroll\' && canAccess(\'payroll\')" x-cloak>'
    end_tag = '<!-- ══ KEY GENERATOR ══ -->'

    start_idx = content.find(start_tag)
    if start_idx == -1:
        print(f"Error: start_tag not found in {filepath}")
        return False

    end_idx = content.find(end_tag, start_idx)
    if end_idx == -1:
        print(f"Error: end_tag not found in {filepath}")
        return False

    # Extract what comes after end_tag
    replacement = new_payroll_html + "\n\n    "
    new_content = content[:start_idx] + replacement + content[end_idx:]

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"Successfully updated {filepath}!")
    return True

if __name__ == '__main__':
    target = 'AdminPanel.html'
    if apply_update(target):
        # Sync to index.html and InvoicePro Admin\AdminPanel.html
        print("Syncing to index.html...")
        shutil.copyfile('AdminPanel.html', 'index.html')
        sub_path = os.path.join('InvoicePro Admin', 'AdminPanel.html')
        if os.path.exists(os.path.dirname(sub_path)):
            print(f"Syncing to {sub_path}...")
            shutil.copyfile('AdminPanel.html', sub_path)
        print("All sync operations completed successfully!")

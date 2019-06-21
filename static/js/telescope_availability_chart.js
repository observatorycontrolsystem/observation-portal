import Vue from 'vue';
import BootstrapVue from 'bootstrap-vue';

import {siteCodeToName, observatoryCodeToNumber, telescopeCodeToName} from './utils.js';
import App from './telescope_availability_chart.vue';

Vue.use(BootstrapVue)

Vue.filter('readableSiteName', function(value){
  let split_string = value.split('.');
  let site = split_string[0];
  let observatory = split_string[1];
  let tel = split_string[2];
  return siteCodeToName[site] + ' ' + telescopeCodeToName[tel] + ' ' + observatoryCodeToNumber[observatory];
});

new Vue({
  el: '#telescope_availability_chart',
  render: function(h){
    return h(App);
  }
});

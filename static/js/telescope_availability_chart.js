import Vue from 'vue';
import {siteCodeToName, observatoryCodeToNumber, telescopeCodeToName} from './utils.js';
import App from './telescope_availability_chart.vue';

Vue.filter('readableSiteName', function(value){
  var split_string = value.split('.');
  var site = split_string[0];
  var observatory = split_string[1];
  var tel = split_string[2];

  return siteCodeToName[site] + ' ' + telescopeCodeToName[tel] + ' ' + observatoryCodeToNumber[observatory];
});

new Vue({
  el: '#telescope_availability_chart',
  render: function(h){
    return h(App);
  }
});


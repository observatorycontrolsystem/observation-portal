<template>
<div class="contention">
  <select v-model="instrument">
    <option value="1M0-SCICAM-SINISTRO">1m Sinistro</option>
    <option value="1M0-NRES-SCICAM"> 1m NRES</option>
    <option value="2M0-SCICAM-SPECTRAL">2m Spectral</option>
    <option value="2M0-FLOYDS-SCICAM">2m FLOYDS</option>
    <option value="0M4-SCICAM-SBIG">.4m SBIG</option>
  </select>
  <i class="fa fa-spin fa-spinner load-spinner" v-show="rawData.length < 1"></i>
  <canvas id="contentionplot" width="400" height="200"></canvas>
</div>
</template>
<script>
import Chart from 'chart.js';
import $ from 'jquery';
import {colorPalette} from '../utils.js';
export default {
  name: 'contention',
  data: function(){
    return {
      instrument: '',
      rawData: [],
      data: {
        labels: Array.apply(null, {length: 24}).map(Number.call, Number),
        datasets: []
      }
    };
  },
  computed: {
    toChartData: function(){
      var datasets = {};
      for (var ra = 0; ra < this.rawData.length; ra++) {
        for(var proposal in this.rawData[ra]){
          if(!datasets.hasOwnProperty(proposal)){
            datasets[proposal] = Array.apply(null, Array(24)).map(Number.prototype.valueOf, 0);  // fills array with 0s
          }
          datasets[proposal][ra] = this.rawData[ra][proposal] / 3600;
        }
      }
      var grouped = [];
      var color = 0;
      for(var prop in datasets){
        grouped.push({label: prop, data: datasets[prop], backgroundColor: colorPalette[color]});
        color++;
      }
      return grouped;
    }
  },
  created: function(){
    this.instrument = '1M0-SCICAM-SINISTRO';
  },
  watch: {
    instrument: function(instrument){
      this.rawData = [];
      var that = this;
      $.getJSON('/api/contention/' + instrument + '/', function(data){
        that.rawData = data.contention_data;
        that.data.datasets = that.toChartData;
        that.chart.update();
      });
    }
  },
  mounted: function(){
    var that = this;
    var ctx = document.getElementById('contentionplot');
    this.chart = new Chart(ctx, {
      type: 'bar',
      data: that.data,
      options: {
        scales:{
          xAxes: [{
            stacked: true,
            scaleLabel: {
              display: true,
              labelString: 'Right Ascension'
            }
          }],
          yAxes: [{
            stacked: true,
            scaleLabel: {
              display: true,
              labelString: 'Total Requested Hours'
            }
          }]
        },
        tooltips: {
          callbacks: {
            label: function(tooltipItem){
              return that.data.datasets[tooltipItem.datasetIndex].label + ' ' +tooltipItem.yLabel.toFixed(3);
            }
          }
        }
      }
    });
  }
};
</script>

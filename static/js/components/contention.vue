<template>
  <b-container class="contention my-4">
    <b-row>
      <b-col cols="auto" class="p-0 pb-1">
        <b-form-group
          id="contention-instrument-formgroup" 
          class="my-auto"
          label="Instrument"
          label-size="sm"
          label-align-sm="right"
          label-cols-sm="5"
          label-for="instrument"
          label-class="font-weight-bolder"
        >
          <b-form-select
            id="contention-instrument-select" 
            size="sm"
            v-model="instrument"
            field="instrument"
            :options="instrumentTypeOptions"
          />
        </b-form-group>
      </b-col>
      <b-col>
        <dataloadhelp
          :dataAvailable="dataAvailable"
          :loadingDataFailed="loadingDataFailed"
          :isLoading="isLoading"
        />
      </b-col>
    </b-row>
    <canvas id="contentionplot" width="400" height="200"></canvas>
  </b-container>
</template>
<script>
  import Chart from 'chart.js';
  import $ from 'jquery';

  import dataloadhelp from './util/dataloadhelp.vue';
  import { colorPalette } from '../utils.js';

  export default {
    name: 'contention',
    components: {
      dataloadhelp
    },
    data: function() {
      return {
        loadingDataFailed: false,
        isLoading: false,
        instrument: '',
        rawData: [],
        instrumentTypeOptions: [
          {value: '0M4-SCICAM-SBIG', text: '0.4m SBIG'},
          {value: '1M0-SCICAM-SINISTRO', text: '1m Sinistro'},
          {value: '1M0-NRES-SCICAM', text: '1m NRES'},
          {value: '2M0-SCICAM-SPECTRAL', text: '2m Spectral'},
          {value: '2M0-FLOYDS-SCICAM', text: '2m FLOYDS'}
        ],
        data: {
          labels: Array.apply(null, {length: 24}).map(Number.call, Number),
          datasets: []
        }
      };
    },
    computed: {
      toChartData: function() {
        let datasets = {};
        for (let ra = 0; ra < this.rawData.length; ra++) {
          for (let proposal in this.rawData[ra]) {
            if (!datasets.hasOwnProperty(proposal)) {
              datasets[proposal] = Array.apply(null, Array(24)).map(Number.prototype.valueOf, 0);  // fills array with 0s
            }
            datasets[proposal][ra] = this.rawData[ra][proposal] / 3600;
          }
        }
        let grouped = [];
        let color = 0;
        for (let prop in datasets) {
          grouped.push({label: prop, data: datasets[prop], backgroundColor: colorPalette[color]});
          color++;
        }
        return grouped;
      },
      dataAvailable: function() {
        for (let bin in this.rawData) {
          for (let proposal in this.rawData[bin]) {
            if (this.rawData[bin][proposal] > 0) {
              return true;
            }
          }
        }
        return false;
      }
    },
    created: function() {
      this.instrument = '1M0-SCICAM-SINISTRO';
    },
    watch: {
      instrument: function(instrument) {
        this.rawData = [];
        this.isLoading = true;
        let that = this;
        $.getJSON('/api/contention/' + instrument + '/', function(data) {
          that.rawData = data.contention_data;
          that.data.datasets = that.toChartData;
          that.chart.update();
        }).done(function() {
          that.loadingDataFailed = false;
        }).fail(function() {
          that.loadingDataFailed = true;
        }).always(function() {
          that.isLoading = false;
        });
      }
    },
    mounted: function() {
      let that = this;
      let ctx = document.getElementById('contentionplot');
      this.chart = new Chart(ctx, {
        type: 'bar',
        data: that.data,
        options: {
          scales: {
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
              label: function(tooltipItem) {
                return that.data.datasets[tooltipItem.datasetIndex].label + ' ' + tooltipItem.yLabel.toFixed(3);
              }
            }
          }
        }
      });
    }
  };
</script>

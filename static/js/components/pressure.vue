<template>
  <b-container class="pressure my-4">
    <b-row>
      <b-col cols="auto" class="p-0 pb-1">
        <b-form-group
          id="pressure-instrument-formgroup" 
          class="my-auto"
          label="Instrument"
          label-size="sm"
          label-align-sm="right"
          label-cols-sm="5"
          label-for="instrument"
          label-class="font-weight-bolder"
        >
          <b-form-select
            id="pressure-instrument-select" 
            size="sm"
            v-model="instrument"
            field="instrument"
            :options="instrumentTypeOptions"
          />
        </b-form-group>
      </b-col>
      <b-col cols="auto" class="p-0 pb-2">
        <b-form-group
          id="pressure-site-formgroup" 
          class="my-auto"
          label="Site"
          label-size="sm"
          label-align-sm="right"
          label-cols-sm="2"
          label-for="site"
          label-class="font-weight-bolder"
        >
          <b-form-select
            id="pressure-site-select" 
            size="sm"
            v-model="site"
            field="site"
            :options="siteOptions"
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
    <canvas id="pressureplot" width="400" height="200"></canvas>
  </b-container>
</template>
<script>
  import 'chartjs-plugin-annotation';
  import Chart from 'chart.js';
  import $ from 'jquery';

  import dataloadhelp from './util/dataloadhelp.vue';
  import { colorPalette } from '../utils.js';

  export default {
    name: 'pressure',
    components: {
      dataloadhelp
    },
    props: {
      instruments: {
        type: Array,
        required: true,
        description: 'Array of objects with value and text fields, used for instrument select field'
      }
    },
    data: function() {
      return {
        instrument: '',
        loadingDataFailed: false,
        isLoading: false,
        site: '',
        maxY: 1,
        rawData: [],
        rawSiteData: [],
        siteNights: [],
        siteOptions: [
          {value: '', text: 'All'},
          {value: 'coj', text: 'Siding Spring, Australia (coj)'},
          {value: 'cpt', text: 'Sutherland, South Africa (cpt)'},
          {value: 'elp', text: 'McDonald, Texas (elp)'},
          {value: 'lsc', text: 'Cerro Tololo, Chile (lsc)'},
          {value: 'ogg', text: 'Maui, Hawaii (ogg)'},
          {value: 'sor', text: 'Cerro Pachón, Chile (sor)'},
          {value: 'tfn', text: 'Tenerife, Canary Islands (tfn)'}
        ],
        data: {
          datasets: [],
          labels: Array.apply(null, {length: 24 * 4 + 1}).map(Number.call, Number).map(function(x){ return (x / 4).toString(); })
        }
      };
    },
    computed: {
      instrumentTypeOptions: function() {
        let options = [{value: '', text: 'All'}]
        for (let idx in this.instruments) {
          options.push(this.instruments[idx]);
        }
        return options;
      },
      toChartData: function() {
        let datasets = {};
        for (let time = 0; time < this.rawData.length; time++) {
          for (let proposal in this.rawData[time]) {
            if (!datasets.hasOwnProperty(proposal)) {
              datasets[proposal] = Array.apply(null, Array(24 * 4)).map(Number.prototype.valueOf, 0);  // fills array with 0s
            }
            datasets[proposal][time] = this.rawData[time][proposal];
          }
        }
        let grouped = [];
        let color = 0;
        for (let prop in datasets) {
          grouped.push({label: prop, data: datasets[prop], backgroundColor: colorPalette[color], type: 'bar'});
          color++;
        }
        return grouped;
      },
      maxPressureInGraph: function() {
        var maxPressure = 0;
        for (var time = 0; time < this.rawData.length; time++) {
          var pressure = 0;
          for(var proposal in this.rawData[time]){
            pressure += this.rawData[time][proposal];
          }
          if (pressure > maxPressure) {
            maxPressure = pressure;
          }
        }
        return maxPressure;
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
      this.fetchData();
    },
    methods: {
      toSiteNightData: function() {
        let nights = [];
        let siteSpacing = 0.6;
        let height = this.maxY + siteSpacing * 2;
        for (let i = 0; i < this.rawSiteData.length; i++) {
          let longSiteName = '';
          for (let so in this.siteOptions) {
            if (this.siteOptions[so].value == this.rawSiteData[i].name) {
              longSiteName = this.siteOptions[so].text;
              break;
            }
          }
          nights.push({
            name: longSiteName,
            start: this.roundToOneQuarter(this.rawSiteData[i].start).toString(),
            end: this.roundToOneQuarter(this.rawSiteData[i].stop).toString(),
            height: height
          });
          height += siteSpacing;
        }
        this.maxY = Math.ceil(height);
        return nights;
      },
      fetchData: function() {
        this.isLoading = true;
        this.rawData = [];
        this.rawSiteData = [];
        let urlstring = '/api/pressure/?x=0';
        if (this.site) urlstring += ('&site=' + this.site);
        if (this.instrument) urlstring += ('&instrument=' + this.instrument);
        let that = this;
        $.getJSON(urlstring, function(data) {
          that.rawData = data.pressure_data;
          that.rawSiteData = data.site_nights;
          that.maxY = that.maxPressureInGraph;
          that.siteNights = that.toSiteNightData;
          that.data.datasets = that.toChartData;
        }).done(function() {
          that.loadingDataFailed = false;
        }).fail(function() {
          that.loadingDataFailed = true;
        }).always(function() {
          that.isLoading = false;
        });
      },
      updateChart: function() {
        this.chart.options.siteNights = this.siteNights;
        this.chart.options.scales.yAxes[0].ticks.max = this.maxY;
        this.chart.update();
      },
      roundToOneQuarter: function(n) {
        return Math.ceil(n * 4) / 4;
      }
    },
    watch: {
      instrument: function() {
        this.fetchData();
      },
      site: function() {
        this.fetchData();
      }
    },
    updated: function() {
      this.updateChart();
    },
    mounted: function() {
      Chart.pluginService.register({
        afterDraw: function(chart) {

          let xScale = chart.scales['x-axis-0'];
          let yScale = chart.scales['y-axis-0'];
          let startHourOfGraph = '0';
          let endHourOfGraph = '24';
          let textPadding = 3;
          let textX;
          let end;
          let start;
          let height;
          let textHeight;
          let tickWidth;
          let night;

          if (chart.options.siteNights) {
            for (var i = 0; i < chart.options.siteNights.length; i++) {
              night = chart.options.siteNights[i];

              height = yScale.getPixelForValue(night.height);
              start = xScale.getPixelForValue(night.start);
              end = xScale.getPixelForValue(night.end);
              textHeight = height - 14;

              textX = (start + end) / 2;
              tickWidth = 8;

              // Draw the main site-night line.
              chart.chart.ctx.strokeStyle = 'black';
              chart.chart.ctx.lineWidth = 2;
              chart.chart.ctx.beginPath();
              chart.chart.ctx.moveTo(start, height);
              chart.chart.ctx.lineTo(end, height);
              chart.chart.ctx.stroke();

              // Draw the tick at the end of the left side of the line.
              chart.chart.ctx.beginPath();
              chart.chart.ctx.moveTo(start, height - tickWidth / 2);
              chart.chart.ctx.lineTo(start, height + tickWidth / 2);
              chart.chart.ctx.stroke();

              // Draw the tick at the end of the right side of the line.
              chart.chart.ctx.beginPath();
              chart.chart.ctx.moveTo(end, height - tickWidth / 2);
              chart.chart.ctx.lineTo(end, height + tickWidth / 2);
              chart.chart.ctx.stroke();

              // Add the label to the line.
              chart.chart.ctx.fillStyle = 'black';
              chart.chart.ctx.textAlign = 'center';
              if (night.start === startHourOfGraph){
                textX = start + textPadding;
                chart.chart.ctx.textAlign = 'left';
              }
              if (night.end === endHourOfGraph){
                textX = end - textPadding;
                chart.chart.ctx.textAlign = 'right';
              }
              chart.chart.ctx.fillText(night.name, textX, textHeight);
            }
          }
        }
      });
      let that = this;
      let ctx = document.getElementById('pressureplot').getContext('2d');

      this.chart = new Chart(ctx, {
        type: 'bar',
        data: that.data,
        options: {
          annotation: {
            annotations: [{
              type: 'line',
              mode: 'horizontal',
              scaleID: 'y-axis-0',
              value: '1.0',
              borderColor: 'black',
              borderDash: [5, 8],
              borderWidth: 4,
            }]
          },
          scales:{
            xAxes: [{
              stacked: true,
              gridLines: {
                offsetGridLines: false
              },
              scaleLabel: {
                display: true,
                labelString: 'Hours From Now'
              },
              ticks: {
                maxTicksLimit: 25,
                maxRotation: 0,
              }
            }],
            yAxes: [{
              stacked: true,
              scaleLabel: {
                display: true,
                labelString: 'Pressure'
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

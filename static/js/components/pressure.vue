<template>
<div class="pressure">
  <label for="pressure-instrument">Instrument</label>
  <select id="pressure-instrument" v-model="instrument">
    <option value="">All</option>
    <option value="1M0-SCICAM-SINISTRO">1m Sinistro</option>
    <option value="1M0-NRES-SCICAM"> 1m NRES</option>
    <option value="2M0-SCICAM-SPECTRAL">2m Spectral</option>
    <option value="2M0-FLOYDS-SCICAM">2m FLOYDS</option>
    <option value="0M4-SCICAM-SBIG">.4m SBIG</option>
  </select>
  <label for="pressure-site">Site</label>
  <select id="pressure-site" v-model="site">
    <option value="">All</option>
    <option value="coj">Siding Spring, Australia (coj)</option>
    <option value="cpt">Sutherland, South Africa (cpt)</option>
    <option value="elp">McDonald, Texas (elp)</option>
    <option value="lsc">Cerro Tololo, Chile (lsc)</option>
    <option value="ogg">Maui, Hawaii (ogg)</option>
    <option value="sqa">Sedgwick Reserve (sqa)</option>
    <option value="tfn">Tenerife, Canary Islands (tfn)</option>
  </select>
  <i class="fa fa-spin fa-spinner load-spinner" v-show="rawData.length < 1"></i>
  <canvas id="pressureplot" width="400" height="200"></canvas>
</div>
</template>
<script>
import Chart from 'chart.js';
import $ from 'jquery';
import {colorPalette} from '../utils.js';
import 'chartjs-plugin-annotation';

export default {
  name: 'pressure',
  data: function(){
    return {
      instrument: '',
      site: '',
      maxY: 1,
      rawData: [],
      rawSiteData: [],
      siteNights: [],
      data: {
        datasets: [],
        labels: Array.apply(null, {length: 24 * 4 + 1}).map(Number.call, Number).map(function(x){ return (x / 4).toString(); })
      }
    };
  },
  computed: {
    toChartData: function(){
      var datasets = {};
      for (var time = 0; time < this.rawData.length; time++) {
        for(var proposal in this.rawData[time]){
          if(!datasets.hasOwnProperty(proposal)){
            datasets[proposal] = Array.apply(null, Array(24 * 4)).map(Number.prototype.valueOf, 0);  // fills array with 0s
          }
          datasets[proposal][time] = this.rawData[time][proposal];
        }
      }
      var grouped = [];
      var color = 0;
      for(var prop in datasets){
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
    toSiteNightData: function(){
      var nights = [];
      var siteSpacing = 0.6;
      var height = this.maxY + siteSpacing * 2;
      for (var i = 0; i < this.rawSiteData.length; i++) {
        var longSiteName = $('#pressure-site option[value=' + this.rawSiteData[i].name + ']').text();
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
    }
  },
  created: function(){
    this.fetchData();
  },
  methods: {
    fetchData: function(){
      this.rawData = [];
      this.rawSiteData = [];
      var urlstring = '/api/pressure/?x=0';
      if(this.site) urlstring += ('&site=' + this.site);
      if(this.instrument) urlstring += ('&instrument=' + this.instrument);
      var that = this;
      $.getJSON(urlstring, function(data){
        that.rawData = data.pressure_data;
        that.rawSiteData = data.site_nights;
        that.maxY = that.maxPressureInGraph;
        that.siteNights = that.toSiteNightData;
        that.data.datasets = that.toChartData;
      });
    },
    updateChart: function(){
      this.chart.options.siteNights = this.siteNights;
      this.chart.options.scales.yAxes[0].ticks.max = this.maxY;
      this.chart.update();
    },
    roundToOneQuarter: function(n){
      return Math.ceil(n * 4) / 4;
    }
  },
  watch: {
    instrument: function(){
      this.fetchData();
    },
    site: function(){
      this.fetchData();
    }
  },
  updated: function(){
    this.updateChart();
  },
  mounted: function(){

    Chart.pluginService.register({

      afterDraw: function(chart) {
        var xScale = chart.scales['x-axis-0'];
        var yScale = chart.scales['y-axis-0'];
        var startHourOfGraph = '0';
        var endHourOfGraph = '24';
        var textPadding = 3;
        var textX;
        var end;
        var start;
        var height;
        var textHeight;
        var tickWidth;
        var night;

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
    var that = this;
    var ctx = document.getElementById('pressureplot').getContext('2d');

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
            label: function(tooltipItem){
              return that.data.datasets[tooltipItem.datasetIndex].label + ' ' + tooltipItem.yLabel.toFixed(3);
            }
          }
        }
      }
    });
  }
};
</script>
